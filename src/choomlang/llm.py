"""Minimal local LLM client abstraction for runner adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import request

from .errors import RunError


_OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"


class LLMClient(Protocol):
    """Protocol for runner adapters that need model chat completions."""

    def chat(
        self,
        model: str,
        *,
        prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        timeout: float | None = None,
        keep_alive: float | None = None,
    ) -> str:
        """Return assistant text for the supplied chat prompt/messages."""


@dataclass(frozen=True)
class OllamaLLMClient:
    """Simple local Ollama chat client backed by urllib."""

    endpoint: str = _OLLAMA_CHAT_URL

    def chat(
        self,
        model: str,
        *,
        prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        timeout: float | None = None,
        keep_alive: float | None = None,
    ) -> str:
        normalized_messages = _normalize_messages(prompt=prompt, messages=messages)
        payload: dict[str, object] = {
            "model": model,
            "messages": normalized_messages,
            "stream": False,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=raw_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover - exercised through runner behavior
            raise RunError(f"ollama chat request failed: {exc}") from exc

        try:
            data = json.loads(body)
            message = data.get("message", {}) if isinstance(data, dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
        except json.JSONDecodeError as exc:
            raise RunError("ollama chat returned invalid JSON") from exc

        if not isinstance(content, str):
            raise RunError("ollama chat response missing assistant content")
        return content


def _normalize_messages(*, prompt: str | None, messages: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if messages is not None:
        if not messages:
            raise RunError("llm call requires non-empty messages when provided")
        return messages
    if prompt is not None:
        return [{"role": "user", "content": prompt}]
    raise RunError("llm call requires either prompt or messages")

