"""Relay helpers for model-to-model ChoomLang exchanges via Ollama."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib import error, request

from .dsl import DSLParseError
from .translate import dsl_to_json

OLLAMA_URL = "http://localhost:11434"
MAX_MESSAGE_CHARS = 4000


class RelayError(RuntimeError):
    """Raised when relay execution fails."""


class OllamaClient:
    """Minimal Ollama chat client using urllib (stdlib-only)."""

    def __init__(self, base_url: str = OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: list[dict[str, str]], seed: int | None = None) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if seed is not None:
            payload["options"] = {"seed": seed}

        try:
            data = self._post_json("/api/chat", payload)
            content = data.get("message", {}).get("content")
            if isinstance(content, str):
                return content
        except RelayError as exc:
            if "HTTP 404" not in str(exc):
                raise

        # Compatibility fallback for older Ollama endpoints.
        prompt = _messages_to_prompt(messages)
        gen_payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if seed is not None:
            gen_payload["options"] = {"seed": seed}
        data = self._post_json("/api/generate", gen_payload)
        content = data.get("response")
        if not isinstance(content, str):
            raise RelayError("Ollama returned an unexpected response shape")
        return content

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RelayError(f"Ollama request failed ({path}): HTTP {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RelayError(
                f"Could not connect to Ollama at {self.base_url}. Is ollama running?"
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RelayError("Ollama returned non-JSON output") from exc
        if not isinstance(data, dict):
            raise RelayError("Ollama returned a non-object JSON payload")
        return data


def strict_validate_with_retry(
    message: str,
    *,
    strict: bool,
    retry: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate a DSL message and optionally retry once using a correction callback."""
    try:
        return message, dsl_to_json(message)
    except DSLParseError as exc:
        if not strict:
            raise
        if retry is None:
            raise RelayError(f"invalid ChoomLang message: {exc}") from exc

        correction_prompt = (
            "Your previous reply was invalid ChoomLang. "
            "Reply with exactly one valid ChoomLang DSL line and no extra text. "
            f"Error: {exc}. Previous reply: {message!r}"
        )
        corrected = retry(correction_prompt)
        try:
            return corrected, dsl_to_json(corrected)
        except DSLParseError as retry_exc:
            raise RelayError(
                f"model failed strict ChoomLang validation after retry: {retry_exc}"
            ) from retry_exc


def run_relay(
    *,
    client: OllamaClient,
    a_model: str,
    b_model: str,
    turns: int = 6,
    seed: int | None = None,
    system_a: str | None = None,
    system_b: str | None = None,
    start: str | None = None,
    strict: bool = True,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Run A<->B relay and return transcript entries as (speaker, dsl, json)."""
    if turns < 1:
        raise RelayError("turns must be >= 1")

    transcript: list[tuple[str, str, dict[str, Any]]] = []
    histories = {"A": _new_history(system_a), "B": _new_history(system_b)}

    current = start or "ping tool service=relay"
    _, current_json = strict_validate_with_retry(current, strict=True)

    for _ in range(turns):
        for speaker, model, other in (("A", a_model, "B"), ("B", b_model, "A")):
            response = _model_step(
                client=client,
                model=model,
                history=histories[speaker],
                incoming_dsl=current,
                incoming_json=current_json,
                seed=seed,
                strict=strict,
            )
            response, response_json = strict_validate_with_retry(response, strict=strict)
            _append_exchange(histories[speaker], current, response)
            _append_exchange(histories[other], current, response)
            transcript.append((speaker, response, response_json))
            current = response
            current_json = response_json

    return transcript


def _model_step(
    *,
    client: OllamaClient,
    model: str,
    history: list[dict[str, str]],
    incoming_dsl: str,
    incoming_json: dict[str, Any],
    seed: int | None,
    strict: bool,
) -> str:
    prompt = (
        "Reply with exactly one ChoomLang DSL line.\n"
        f"Incoming DSL: {incoming_dsl}\n"
        f"Incoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    )
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]

    def retry_callback(correction_prompt: str) -> str:
        correction_history = [
            *working_history,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": correction_prompt},
        ]
        return _clip_model_output(client.chat(model, correction_history, seed=seed))

    raw = _clip_model_output(client.chat(model, working_history, seed=seed))
    validated, _ = strict_validate_with_retry(raw, strict=strict, retry=retry_callback if strict else None)
    return validated


def _append_exchange(history: list[dict[str, str]], incoming: str, outgoing: str) -> None:
    history.append({"role": "user", "content": incoming})
    history.append({"role": "assistant", "content": outgoing})


def _new_history(system_prompt: str | None) -> list[dict[str, str]]:
    if not system_prompt:
        return []
    return [{"role": "system", "content": system_prompt}]


def _clip_model_output(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_MESSAGE_CHARS:
        raise RelayError("model message exceeded maximum size")
    return text


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
