"""Relay helpers for model-to-model ChoomLang exchanges via Ollama."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

from .dsl import DSLParseError
from .protocol import build_guard_prompt, canonical_json_schema
from .translate import json_to_dsl

OLLAMA_URL = "http://localhost:11434"
MAX_MESSAGE_CHARS = 4000


class RelayError(RuntimeError):
    """Raised when relay execution fails."""


class OllamaClient:
    """Minimal Ollama chat client using urllib (stdlib-only)."""

    def __init__(self, base_url: str = OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        seed: int | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if seed is not None:
            payload["options"] = {"seed": seed}
        if response_format is not None:
            payload["format"] = response_format

        try:
            data = self._post_json("/api/chat", payload)
            content = data.get("message", {}).get("content")
            if isinstance(content, str):
                return content
        except RelayError as exc:
            if "HTTP 404" not in str(exc):
                raise

        if response_format is not None:
            raise RelayError("structured relay requires Ollama /api/chat endpoint support")

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
    lenient: bool = False,
    retry: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate a DSL message and optionally retry once using a correction callback."""
    try:
        return message, dsl_to_json_with_options(message, lenient=lenient)
    except DSLParseError as exc:
        if not strict:
            raise
        if retry is None:
            raise RelayError(f"invalid ChoomLang message: {exc}") from exc

        correction_prompt = build_guard_prompt(error=str(exc), previous=message)
        corrected = retry(correction_prompt)
        try:
            return corrected, dsl_to_json_with_options(corrected, lenient=lenient)
        except DSLParseError as retry_exc:
            raise RelayError(
                f"model failed strict ChoomLang validation after retry: {retry_exc}"
            ) from retry_exc


def dsl_to_json_with_options(message: str, *, lenient: bool) -> dict[str, Any]:
    from .dsl import parse_dsl

    return parse_dsl(message, lenient=lenient).to_json_dict()


def parse_structured_reply(raw: str) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RelayError("structured relay response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RelayError("structured relay response must be a JSON object")

    if "op" not in payload or "target" not in payload:
        raise RelayError("structured relay response missing required keys: op and target")

    normalized = {
        "op": str(payload["op"]),
        "target": str(payload["target"]),
        "count": payload.get("count", 1),
        "params": payload.get("params", {}),
    }

    try:
        normalized["count"] = int(normalized["count"])
    except (TypeError, ValueError) as exc:
        raise RelayError("structured relay response count must be an integer") from exc
    if normalized["count"] < 1:
        raise RelayError("structured relay response count must be >= 1")

    if not isinstance(normalized["params"], dict):
        raise RelayError("structured relay response params must be an object")

    dsl = json_to_dsl(normalized)
    return normalized, dsl


def build_transcript_record(
    *,
    side: str,
    model: str,
    mode: str,
    raw: str,
    parsed: dict[str, Any] | None,
    dsl: str | None,
    error: str | None,
    retry: int,
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "side": side,
        "model": model,
        "mode": mode,
        "raw": raw,
        "parsed": parsed,
        "dsl": dsl,
        "error": error,
        "retry": retry,
    }


def append_transcript(path: str | None, record: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


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
    structured: bool = False,
    use_schema: bool = True,
    raw_json: bool = False,
    log_path: str | None = None,
    lenient: bool = False,
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    """Run A<->B relay and return transcript entries."""
    if turns < 1:
        raise RelayError("turns must be >= 1")

    transcript: list[tuple[str, str, dict[str, Any], str | None]] = []
    histories = {"A": _new_history(system_a), "B": _new_history(system_b)}

    current = start or "ping tool service=relay"
    _, current_json = strict_validate_with_retry(current, strict=True, lenient=lenient)

    for _ in range(turns):
        for speaker, model, other in (("A", a_model, "B"), ("B", b_model, "A")):
            if structured:
                response_raw, response, response_json = _structured_model_step(
                    client=client,
                    model=model,
                    history=histories[speaker],
                    incoming_json=current_json,
                    seed=seed,
                    use_schema=use_schema,
                )
                mode = "structured"
                next_incoming = json.dumps(response_json, sort_keys=True)
            else:
                response_raw, response, response_json = _dsl_model_step(
                    client=client,
                    model=model,
                    history=histories[speaker],
                    incoming_dsl=current,
                    incoming_json=current_json,
                    seed=seed,
                    strict=strict,
                    lenient=lenient,
                    side=speaker,
                    log_path=log_path,
                )
                mode = "dsl"
                next_incoming = response

            _append_exchange(histories[speaker], current, next_incoming)
            _append_exchange(histories[other], current, next_incoming)
            transcript.append((speaker, response, response_json, response_raw if raw_json else None))

            retry_value = 1 if (mode == "dsl" and response_raw != response) else 0
            append_transcript(
                log_path,
                build_transcript_record(
                    side=speaker,
                    model=model,
                    mode=mode,
                    raw=response_raw,
                    parsed=response_json,
                    dsl=response,
                    error=None,
                    retry=retry_value,
                ),
            )

            current = next_incoming if structured else response
            current_json = response_json

    return transcript


def _structured_model_step(
    *,
    client: OllamaClient,
    model: str,
    history: list[dict[str, str]],
    incoming_json: dict[str, Any],
    seed: int | None,
    use_schema: bool,
) -> tuple[str, str, dict[str, Any]]:
    prompt = (
        "Reply with exactly one canonical ChoomLang JSON object and no extra text.\n"
        f"Incoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    )
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    response_format: str | dict[str, Any] = canonical_json_schema() if use_schema else "json"
    working_history = [*history, {"role": "user", "content": prompt}]
    raw = _clip_model_output(
        client.chat(model, working_history, seed=seed, response_format=response_format)
    )
    payload, dsl = parse_structured_reply(raw)
    return raw, dsl, payload


def _dsl_model_step(
    *,
    client: OllamaClient,
    model: str,
    history: list[dict[str, str]],
    incoming_dsl: str,
    incoming_json: dict[str, Any],
    seed: int | None,
    strict: bool,
    lenient: bool,
    side: str,
    log_path: str | None,
) -> tuple[str, str, dict[str, Any]]:
    prompt = (
        "Reply with exactly one ChoomLang DSL line.\n"
        f"Incoming DSL: {incoming_dsl}\n"
        f"Incoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    )
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]
    raw = _clip_model_output(client.chat(model, working_history, seed=seed))

    try:
        payload = dsl_to_json_with_options(raw, lenient=lenient)
    except DSLParseError as exc:
        append_transcript(
            log_path,
            build_transcript_record(
                side=side,
                model=model,
                mode="dsl",
                raw=raw,
                parsed=None,
                dsl=None,
                error=str(exc),
                retry=0,
            ),
        )
        if not strict:
            raise

        correction_prompt = build_guard_prompt(error=str(exc), previous=raw)
        correction_history = [
            *working_history,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": correction_prompt},
        ]
        corrected = _clip_model_output(client.chat(model, correction_history, seed=seed))
        try:
            payload = dsl_to_json_with_options(corrected, lenient=lenient)
            return corrected, corrected, payload
        except DSLParseError as retry_exc:
            append_transcript(
                log_path,
                build_transcript_record(
                    side=side,
                    model=model,
                    mode="dsl",
                    raw=corrected,
                    parsed=None,
                    dsl=None,
                    error=str(retry_exc),
                    retry=1,
                ),
            )
            raise RelayError(
                f"model failed strict ChoomLang validation after retry: {retry_exc}"
            ) from retry_exc

    return raw, raw, payload


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
