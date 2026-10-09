"""A scripted stand-in for the AI provider, so the agent loop can be tested deterministically."""

import hashlib
import re
from collections.abc import AsyncIterator
from typing import Any

from app.rag import prompts
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
    ) -> None:
        self.plans = list(plans or [])
        self.grades = list(grades or [])
        self.answer = answer
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
        queue = self.plans if system == prompts.QUERY_SYSTEM else self.grades
        if not queue:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return queue.pop(0)

    async def stream_completion(self, system: str, user: str, *, temperature: float | None = None) -> AsyncIterator[str]:
        self.stream_calls.append(user)
        self.temperatures.append((system, temperature))
        for count, start in enumerate(range(0, len(self.answer), self.stream_size)):
            if self.fail_stream_after is not None and count >= self.fail_stream_after:
                raise LLMError("The AI provider took too long to respond. Please try again.")
            yield self.answer[start : start + self.stream_size]

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
