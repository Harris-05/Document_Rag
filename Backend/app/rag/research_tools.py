"""The tools the research agent can call, and the checks that make a bad call harmless.

A model's tool calls cannot be trusted: the name may not exist, the arguments may not be JSON, a
required argument may be missing, or the values may be nonsense. Every call goes through `run`, which
never raises. A bad call comes back as a plain message telling the model what was wrong and what the
tool expects, so it can correct itself, and the caller counts it against a budget of bad calls.

Everything a tool shows the model is registered as numbered evidence (E1, E2, ...). The final answer is
written from that evidence and its quotes are verified against the document, so the answer can only be
as good as what the model actually read.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.compare.segment import Unit
from app.config import Settings
from app.rag.index import DocumentIndex
from app.rag.llm import LLMClient, LLMError

_NUMBER = re.compile(r"^\s*(?:(?:article|section|clause)\s+)?(\d+(?:\.\d+)*)\.?(?:\s|$)", re.IGNORECASE)
MAX_LISTED_CLAUSES = 120


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchArgs(_Args):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=8)


class SectionArgs(_Args):
    number: str = Field(min_length=1, max_length=60)


class ListArgs(_Args):
    pass


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": (
                "Search the contract for passages about a topic. Use short queries in the wording a "
                "contract would use (for example 'termination for convenience notice period'). Returns "
                "the best matching passages with their page and section heading."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for."},
                    "max_results": {"type": "integer", "description": "How many passages to return, 1 to 8 (default 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_section",
            "description": (
                "Read one numbered section or clause in full, including its sub-clauses. Pass the "
                "number as shown by list_clauses or in a search result, such as '12' or '12.3'. A "
                "heading such as 'Termination' also works."
            ),
            "parameters": {
                "type": "object",
                "properties": {"number": {"type": "string", "description": "Clause number, or a heading."}},
                "required": ["number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clauses",
            "description": (
                "List the numbered clauses and headings of the contract with their pages, as a table of "
                "contents. Takes no arguments. Use it to see how the contract is organised."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_NAMES = [spec["function"]["name"] for spec in TOOL_SPECS]
_ARG_MODELS: dict[str, type[_Args]] = {
    "search_document": SearchArgs,
    "get_section": SectionArgs,
    "list_clauses": ListArgs,
}
_EXAMPLES = {
    "search_document": '{"query": "termination notice period"}',
    "get_section": '{"number": "12.1"}',
    "list_clauses": "{}",
}


@dataclass(frozen=True)
class Evidence:
    label: str
    page: int
    text: str
    context: str
    section: bool = False


@dataclass
class ToolOutcome:
    """What one call produced. `ok` is False for a bad call, which counts against the budget."""

    ok: bool
    message: str  # shown to the model
    summary: str  # shown to the user
    repeat: bool = False


@dataclass
class _Section:
    number: str
    title: str
    page: int
    units: list[Unit] = field(default_factory=list)


def _number_of(unit: Unit) -> str | None:
    for text in (unit.heading, unit.text):
        match = _NUMBER.match(text or "")
        if match:
            return match.group(1)
    return None


def _title_of(unit: Unit) -> str:
    first = (unit.heading or unit.text).strip().splitlines()[0]
    return _NUMBER.sub("", first, count=1).strip(" .:-")[:80]


def _describe(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "arguments"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def _build_sections(units: list[Unit]) -> list[_Section]:
    sections: list[_Section] = []
    for unit in units:
        number = _number_of(unit)
        if number is not None and (unit.starts_clause or not sections):
            sections.append(_Section(number, _title_of(unit), unit.page, [unit]))
        elif sections:
            sections[-1].units.append(unit)
        elif unit.heading:
            sections.append(_Section("", _title_of(unit), unit.page, [unit]))
    return sections


class DocumentTools:
    """Tool implementations for one document. Holds the numbered evidence handed to the model."""

    def __init__(self, index: DocumentIndex, units: list[Unit], llm: LLMClient, settings: Settings) -> None:
        self._index = index
        self._llm = llm
        self._settings = settings
        self._sections = _build_sections(units)
        self.evidence: dict[str, Evidence] = {}
        self._labels: dict[tuple[str, str], str] = {}
        self._done: set[str] = set()
        self.keyword_only = not index.has_embeddings

    def _register(self, kind: str, key: str, page: int, text: str, context: str) -> tuple[str, bool]:
        existing = self._labels.get((kind, key))
        if existing:
            return existing, False
        label = f"E{len(self.evidence) + 1}"
        self._labels[(kind, key)] = label
        self.evidence[label] = Evidence(label, page, text, context, section=kind == "section")
        return label, True

    async def run(self, name: str, raw_arguments: str) -> ToolOutcome:
        """Runs one call. Never raises: every kind of bad call becomes a message for the model."""
        if name not in _ARG_MODELS:
            return ToolOutcome(
                False,
                f"Error: there is no tool named {name!r}. The available tools are: {', '.join(TOOL_NAMES)}.",
                f"The model asked for a tool that does not exist ({name or 'no name'}); it was told what is available",
            )
        try:
            parsed: Any = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError:
            return ToolOutcome(
                False,
                f"Error: the arguments for {name} were not valid JSON. Send a JSON object, for example {_EXAMPLES[name]}.",
                f"The arguments for {name} were not valid JSON; the model was asked to try again",
            )
        if not isinstance(parsed, dict):
            return ToolOutcome(
                False,
                f"Error: the arguments for {name} must be a JSON object, for example {_EXAMPLES[name]}.",
                f"The arguments for {name} had the wrong shape; the model was asked to try again",
            )
        try:
            args = _ARG_MODELS[name].model_validate(parsed)
        except ValidationError as error:
            detail = _describe(error)
            return ToolOutcome(
                False,
                f"Error: invalid arguments for {name} ({detail}). Example: {_EXAMPLES[name]}.",
                f"Invalid arguments for {name} ({detail}); the model was asked to correct them",
            )

        signature = f"{name}:{json.dumps(args.model_dump(), sort_keys=True)}"
        if signature in self._done:
            return ToolOutcome(
                True,
                "You already made this exact call and its results are above. Try a different query or section.",
                "Repeated an earlier lookup, skipped",
                repeat=True,
            )
        self._done.add(signature)

        if isinstance(args, SearchArgs):
            return await self._search(args)
        if isinstance(args, SectionArgs):
            return self._section(args)
        return self._list()

    async def _search(self, args: SearchArgs) -> ToolOutcome:
        vectors = None
        if self._index.has_embeddings:
            try:
                vectors = await self._llm.embed([args.query])
            except LLMError:
                self.keyword_only = True
        hits = self._index.search([args.query], vectors, args.max_results)
        if not hits:
            return ToolOutcome(True, f"No passages matched {args.query!r}. Try different words.", f"Nothing found for “{args.query}”")

        limit = self._settings.research_passage_chars
        blocks: list[str] = []
        pages: set[int] = set()
        fresh = 0
        for hit in hits:
            chunk = hit.chunk
            label, is_new = self._register("chunk", str(chunk.id), chunk.page_number, chunk.text, chunk.context)
            pages.add(chunk.page_number)
            header = f"[{label}] page {chunk.page_number}" + (f" | section: {chunk.context}" if chunk.context else "")
            if is_new:
                fresh += 1
                body = chunk.text if len(chunk.text) <= limit else chunk.text[:limit].rstrip() + " ..."
                blocks.append(f"{header}\n{body}")
            else:
                blocks.append(f"{header}\n(shown earlier)")
        shown = ", ".join(str(p) for p in sorted(pages))
        return ToolOutcome(
            True,
            f"{len(hits)} passages for {args.query!r}:\n\n" + "\n\n".join(blocks),
            f"Found {len(hits)} passage{'s' if len(hits) != 1 else ''} on page{'s' if len(pages) != 1 else ''} {shown}"
            + (f" ({fresh} new)" if fresh != len(hits) else ""),
        )

    def _find_section(self, query: str) -> _Section | None:
        wanted = query.strip().lower()
        for prefix in ("section ", "clause ", "article "):
            wanted = wanted.removeprefix(prefix)
        wanted = wanted.strip(" .")
        for section in self._sections:
            if section.number and section.number == wanted:
                return section
        for section in self._sections:
            if wanted and section.title and wanted in section.title.lower():
                return section
        return None

    def _section(self, args: SectionArgs) -> ToolOutcome:
        section = self._find_section(args.number)
        if section is None:
            known = [s.number for s in self._sections if s.number][:30]
            hint = f" Numbered clauses: {', '.join(known)}." if known else " Use list_clauses or search_document instead."
            return ToolOutcome(
                True,
                f"There is no section {args.number!r} in this contract.{hint}",
                f"No section “{args.number}” exists; the model was shown what does",
            )

        # A section includes its sub-clauses: asking for "12" also returns 12.1, 12.2 and so on.
        group = [section]
        if section.number:
            prefix = section.number + "."
            group += [s for s in self._sections if s.number.startswith(prefix)]
        text = "\n".join(unit.text for member in group for unit in member.units)
        limit = self._settings.research_section_chars
        truncated = len(text) > limit
        if truncated:
            text = text[:limit].rstrip() + " ..."
        title = f"{section.number}. {section.title}" if section.number else section.title
        label, _ = self._register("section", section.number or section.title, section.page, text, title)
        note = "\n[Section cut short. Ask for a sub-clause number to read the rest.]" if truncated else ""
        return ToolOutcome(
            True,
            f"[{label}] page {section.page} | section: {title}\n{text}{note}",
            f"Read section {title}" + (" (cut short)" if truncated else ""),
        )

    def _list(self) -> ToolOutcome:
        if not self._sections:
            return ToolOutcome(
                True,
                "This contract has no numbered clauses or headings that could be listed. Use search_document.",
                "The contract has no numbered clauses to list",
            )
        shown = self._sections[:MAX_LISTED_CLAUSES]
        lines = [f"{s.number + '. ' if s.number else ''}{s.title} (page {s.page})" for s in shown]
        extra = len(self._sections) - len(shown)
        more = f"\n... and {extra} more" if extra > 0 else ""
        return ToolOutcome(
            True,
            "Clauses:\n" + "\n".join(lines) + more,
            f"Listed {len(lines)} clause{'s' if len(lines) != 1 else ''}",
        )
