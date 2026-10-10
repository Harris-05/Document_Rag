"""The only place that talks to an AI provider.

The agent depends on the small `LLMClient` protocol, so the whole retrieve-grade-correct loop can be
tested with a scripted fake and the provider can be swapped without touching it.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    RateLimitError,
)

from app.config import Settings


class LLMError(Exception):
    """A provider failure with a message that is safe to show the user."""

    def __init__(self, message: str, *, configured: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.configured = configured


@dataclass(frozen=True)
class ToolCall:
    """One tool call the model asked for. `arguments` is the raw string: it may not be valid JSON."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolTurn:
    content: str
    tool_calls: list[ToolCall]


class LLMClient(Protocol):
    async def tool_completion(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, temperature: float | None = None
    ) -> ToolTurn: ...

    async def json_completion(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> dict[str, Any]: ...

    def stream_completion(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> AsyncIterator[str]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _translate(error: Exception) -> LLMError:
    if isinstance(error, AuthenticationError):
        return LLMError("The AI provider rejected the API key. Check OPENAI_API_KEY in Backend/.env.")
    if isinstance(error, RateLimitError):
        return LLMError("The AI provider is rate limiting requests or the quota is used up. Try again shortly.")
    if isinstance(error, NotFoundError):
        return LLMError("The configured AI model was not found. Check OPENAI_MODEL in Backend/.env.")
    if isinstance(error, APITimeoutError):
        return LLMError("The AI provider took too long to respond. Please try again.")
    if isinstance(error, APIConnectionError):
        return LLMError("Could not reach the AI provider. Check the network and OPENAI_BASE_URL.")
    return LLMError("The AI provider returned an error. Please try again.")


class OpenAIClient:
    """An OpenAI-compatible client (OpenAI, OpenRouter, a local server, and similar)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )
        self._temperature_supported = True

    async def _create(self, temperature: float | None, **kwargs: Any) -> Any:
        """Chat completion with a temperature, retrying without one if the model rejects it.

        Some models (for example reasoning models) only accept their default temperature and answer
        any other value with a 400. That is remembered so later calls skip the failed attempt.
        """
        if temperature is not None and self._temperature_supported:
            try:
                return await self._client.chat.completions.create(temperature=temperature, **kwargs)
            except BadRequestError as error:
                if "temperature" not in str(error).lower():
                    raise
                self._temperature_supported = False
        return await self._client.chat.completions.create(**kwargs)

    async def json_completion(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> dict[str, Any]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = await self._create(
                    temperature,
                    model=self._settings.openai_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
            except OpenAIError as error:
                raise _translate(error) from error
            content = response.choices[0].message.content or ""
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as error:
                last_error = error
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": "That was not a valid JSON object. Reply again with only the JSON object."},
            ]
        raise LLMError("The AI model returned an unreadable response. Please try again.") from last_error

    async def tool_completion(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, temperature: float | None = None
    ) -> ToolTurn:
        try:
            response = await self._create(
                temperature,
                model=self._settings.openai_model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except OpenAIError as error:
            raise _translate(error) from error
        message = response.choices[0].message
        calls = [
            ToolCall(id=call.id, name=call.function.name or "", arguments=call.function.arguments or "")
            for call in (message.tool_calls or [])
            if getattr(call, "function", None) is not None
        ]
        return ToolTurn(content=message.content or "", tool_calls=calls)

    async def stream_completion(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> AsyncIterator[str]:
        try:
            stream = await self._create(
                temperature,
                model=self._settings.openai_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                stream=True,
            )
            async for event in stream:
                if event.choices and event.choices[0].delta.content:
                    yield event.choices[0].delta.content
        except OpenAIError as error:
            raise _translate(error) from error

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), 96):
                response = await self._client.embeddings.create(
                    model=self._settings.openai_embedding_model, input=texts[start : start + 96]
                )
                vectors.extend(item.embedding for item in response.data)
        except OpenAIError as error:
            raise _translate(error) from error
        return vectors


def build_llm_client(settings: Settings) -> LLMClient:
    if not settings.openai_api_key:
        raise LLMError(
            "The AI provider is not configured. Add OPENAI_API_KEY to Backend/.env and restart the server.",
            configured=False,
        )
    return OpenAIClient(settings)
