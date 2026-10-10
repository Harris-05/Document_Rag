"""A scripted stand-in for the AI provider, so the agent loop can be tested deterministically."""

import hashlib
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.rag import prompts, prompts_multi
from app.rag.llm import LLMError


class FakeLLM:
    def __init__(
        self,
        *,
        plans: list[dict[str, Any]] | None = None,
        grades: list[dict[str, Any]] | None = None,
        answer: str = "",
        embeddings_fail: bool = False,
        stream_size: int = 7,
        fail_stream_after: int | None = None,
        answer_for: Callable[[str], str] | None = None,
        json_handler: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.plans = list(plans or [])
        self.grades = list(grades or [])
        self.answer = answer
        self.answer_for = answer_for
        self.json_handler = json_handler
        self.embeddings_fail = embeddings_fail
        self.stream_size = stream_size
        self.fail_stream_after = fail_stream_after
        self.json_calls: list[tuple[str, str]] = []
        self.stream_calls: list[str] = []
        self.embed_calls = 0
        self.embedded_texts: list[str] = []
        self.temperatures: list[tuple[str, float | None]] = []

    async def json_completion(self, system: str, user: str, *, temperature: float | None = None) -> dict[str, Any]:
        self.json_calls.append((system, user))
        self.temperatures.append((system, temperature))
        if self.json_handler is not None:
            return self.json_handler(system, user)
        queue = self.plans if system == prompts.QUERY_SYSTEM else self.grades
        if not queue:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return queue.pop(0)

    async def stream_completion(self, system: str, user: str, *, temperature: float | None = None) -> AsyncIterator[str]:
        self.stream_calls.append(user)
        self.temperatures.append((system, temperature))
        answer = self.answer_for(user) if self.answer_for else self.answer
        for count, start in enumerate(range(0, len(answer), self.stream_size)):
            if self.fail_stream_after is not None and count >= self.fail_stream_after:
                raise LLMError("The AI provider took too long to respond. Please try again.")
            yield answer[start : start + self.stream_size]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += 1
        self.embedded_texts.extend(texts)
        if self.embeddings_fail:
            raise LLMError("embeddings unavailable")
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str, dims: int = 64) -> list[float]:
        vector = [0.0] * dims
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % dims
            vector[slot] += 1.0
        return vector

    # Convenience for assertions.
    def count(self, system: str) -> int:
        return sum(1 for s, _ in self.json_calls if s == system)

    def prompts_for(self, system: str) -> list[str]:
        return [u for s, u in self.json_calls if s == system]


class ScriptedGrader(FakeLLM):
    """Resolves page numbers in scripted grades to real chunk ids at call time."""

    async def json_completion(self, system, user, **kwargs):
        result = await super().json_completion(system, user, **kwargs)
        if system == prompts.GRADE_SYSTEM and "page" in result:
            page = result["page"]
            ids = {int(p): int(i) for i, p in re.findall(r"\[passage (\d+)\] \(page (\d+)\)", user)}
            grades = [{"id": cid, "score": 0} for cid in ids.values()]
            for grade in grades:
                if ids.get(page) == grade["id"]:
                    grade["score"] = result["score"]
            return {"grades": grades, "sufficient": result["sufficient"], "missing": result["missing"]}
        return result


class ScriptedMultiGrader(FakeLLM):
    """Scripts the multi-document judge by (document label, page) instead of by opaque passage ids.

    A scripted grade looks like
        {"scores": {"D1": {2: 2}}, "sufficient": {"D1": True, "D2": False}, "missing": {"D2": "..."}}
    meaning: in D1, the passage on page 2 scores 2.
    """

    async def json_completion(self, system, user, **kwargs):
        result = await super().json_completion(system, user, **kwargs)
        if system == prompts_multi.GRADE_MULTI_SYSTEM and "scores" in result:
            grades = []
            blocks = re.findall(r'=== (D\d+): "[^"]*" ===\n\n(.*?)(?=\n\n=== D|\Z)', user, re.S)
            for label, block in blocks:
                for pid, page in re.findall(r"\[passage (\d+)\] \(page (\d+)\)", block):
                    spec = result["scores"].get(label, {})
                    # An int scores every passage shown for that document; a dict scores by page.
                    score = spec if isinstance(spec, int) else spec.get(int(page), 0)
                    if score:
                        grades.append({"id": int(pid), "score": score})
            return {"grades": grades, "sufficient": result["sufficient"], "missing": result.get("missing", {})}
        return result


def evidence_label(prompt: str, document: str, page: int | None = None) -> str:
    """The E-number the prompt gave to the first passage from `document` (on `page`, if given)."""
    where = r"[^\n]*" if page is None else rf", page {page}\b"
    match = re.search(rf'\[(E\d+)\] Document {document} "[^"]*"{where}', prompt)
    assert match, f"no evidence for {document} page {page} in the prompt"
    return match.group(1)
