"""Relay helpers for model-to-model ChoomLang exchanges via Ollama."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal
from urllib import error, request

from .dsl import DSLParseError
from .protocol import build_contract_prompt, build_guard_prompt, canonical_json_schema
from .translate import json_to_dsl

OLLAMA_URL = "http://localhost:11434"
MAX_MESSAGE_CHARS = 4000
RequestMode = Literal["dsl", "structured-schema", "structured-json", "fallback-dsl"]


class RelayError(RuntimeError):
    """Raised when relay execution fails."""


class OllamaClient:
    """Minimal Ollama chat client using urllib (stdlib-only)."""

    def __init__(
        self,
        base_url: str = OLLAMA_URL,
        *,
        timeout: float = 180.0,
        keep_alive: float | None = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        seed: int | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        options: dict[str, Any] = {}
        if seed is not None:
            options["seed"] = seed
        if options:
            payload["options"] = options
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        if response_format is not None:
            payload["format"] = response_format

        try:
            data, elapsed_ms = self._post_json("/api/chat", payload)
            content = data.get("message", {}).get("content")
            if isinstance(content, str):
                return content, elapsed_ms
        except RelayError as exc:
            if "HTTP 404" not in str(exc):
                raise

        if response_format is not None:
            raise RelayError("structured relay requires Ollama /api/chat endpoint support")

        prompt = _messages_to_prompt(messages)
        gen_payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if seed is not None:
            gen_payload["options"] = {"seed": seed}
        if self.keep_alive is not None:
            gen_payload["keep_alive"] = self.keep_alive

        data, elapsed_ms = self._post_json("/api/generate", gen_payload)
        content = data.get("response")
        if not isinstance(content, str):
            raise RelayError("Ollama returned an unexpected response shape")
        return content, elapsed_ms

    def _post_json(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = perf_counter()
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RelayError(f"Ollama request failed ({path}): HTTP {exc.code} {detail}") from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                raise RelayError(f"Ollama request timed out after {self.timeout:g}s") from exc
            raise RelayError(
                f"Could not connect to Ollama at {self.base_url}. Is ollama running?"
            ) from exc
        except TimeoutError as exc:
            raise RelayError(f"Ollama request timed out after {self.timeout:g}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RelayError("Ollama returned non-JSON output") from exc
        if not isinstance(data, dict):
            raise RelayError("Ollama returned a non-object JSON payload")
        return data, int((perf_counter() - started) * 1000)


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


def decide_structured_recovery(
    *,
    schema_failed: bool,
    json_failed: bool,
    strict: bool,
    fallback_enabled: bool,
) -> str:
    """Pure fallback decision helper for structured relay stage failures."""
    if not schema_failed:
        return "schema-ok"
    if not fallback_enabled:
        return "fail-no-fallback"
    if not json_failed:
        return "retry-json"
    if strict:
        return "fail-strict"
    return "fallback-dsl"


def build_transcript_record(
    *,
    side: str,
    model: str,
    mode: str,
    request_mode: RequestMode,
    raw: str,
    parsed: dict[str, Any] | None,
    dsl: str | None,
    error: str | None,
    retry: int,
    elapsed_ms: int,
    timeout_s: float,
    keep_alive_s: float | None,
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "side": side,
        "model": model,
        "mode": mode,
        "request_mode": request_mode,
        "raw": raw,
        "parsed": parsed,
        "dsl": dsl,
        "error": error,
        "retry": retry,
        "elapsed_ms": elapsed_ms,
        "timeout_s": timeout_s,
        "keep_alive_s": keep_alive_s,
    }


def append_transcript(path: str | None, record: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    with target.open("a", encoding="utf-8", buffering=1) as fh:
        fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()


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
    fallback_enabled: bool = True,
    use_contract_in_structured: bool = True,
    raw_json: bool = False,
    log_path: str | None = None,
    lenient: bool = False,
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    """Run A<->B relay and return transcript entries."""
    if turns < 1:
        raise RelayError("turns must be >= 1")

    if not structured:
        contract = build_contract_prompt("dsl")
        if system_a is None:
            system_a = contract
        if system_b is None:
            system_b = contract

    transcript: list[tuple[str, str, dict[str, Any], str | None]] = []
    histories = {"A": _new_history(system_a), "B": _new_history(system_b)}

    current = start or "ping tool service=relay"
    _, current_json = strict_validate_with_retry(current, strict=True, lenient=lenient)

    for _ in range(turns):
        for speaker, model, other in (("A", a_model, "B"), ("B", b_model, "A")):
            if structured:
                response_raw, response, response_json, elapsed_ms, request_mode = _structured_model_step(
                    client=client,
                    model=model,
                    history=histories[speaker],
                    incoming_json=current_json,
                    seed=seed,
                    use_schema=use_schema,
                    strict=strict,
                    fallback_enabled=fallback_enabled,
                    lenient=lenient,
                    add_contract=use_contract_in_structured,
                )
                mode = "structured"
                next_incoming = json.dumps(response_json, sort_keys=True)
            else:
                response_raw, response, response_json, elapsed_ms = _dsl_model_step(
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
                request_mode = "dsl"
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
                    request_mode=request_mode,
                    raw=response_raw,
                    parsed=response_json,
                    dsl=response,
                    error=None,
                    retry=retry_value,
                    elapsed_ms=elapsed_ms,
                    timeout_s=client.timeout,
                    keep_alive_s=client.keep_alive,
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
    strict: bool,
    fallback_enabled: bool,
    lenient: bool,
    add_contract: bool,
) -> tuple[str, str, dict[str, Any], int, RequestMode]:
    contract = build_contract_prompt("structured") if add_contract else ""
    prompt = (
        "Reply with exactly one canonical ChoomLang JSON object and no extra text.\n"
        f"{contract}\nIncoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    ).strip()
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]

    if use_schema:
        schema_format = canonical_json_schema()
        try:
            raw_schema, elapsed_schema = _chat_once(
                client, model, working_history, seed=seed, response_format=schema_format
            )
            payload, dsl = parse_structured_reply(raw_schema)
            return raw_schema, dsl, payload, elapsed_schema, "structured-schema"
        except RelayError as schema_err:
            if not fallback_enabled:
                raise RelayError(f"structured schema stage failed: {schema_err}") from schema_err

            print(
                f"warning: structured schema stage failed ({schema_err}); retrying with format=json",
                file=sys.stderr,
            )

            try:
                raw_json, elapsed_json = _chat_once(
                    client, model, working_history, seed=seed, response_format="json"
                )
                payload, dsl = parse_structured_reply(raw_json)
                return raw_json, dsl, payload, elapsed_json, "structured-json"
            except RelayError as json_err:
                decision = decide_structured_recovery(
                    schema_failed=True,
                    json_failed=True,
                    strict=strict,
                    fallback_enabled=fallback_enabled,
                )
                if decision == "fail-strict":
                    raise RelayError(
                        "structured relay failed at stage structured-json after schema retry; "
                        f"last raw response: {raw_json if 'raw_json' in locals() else '<none>'}"
                    ) from json_err
                if decision == "fallback-dsl":
                    print(
                        "warning: structured json stage failed; falling back to DSL guard mode",
                        file=sys.stderr,
                    )
                    raw_dsl, dsl_line, payload, elapsed_dsl = _dsl_model_step(
                        client=client,
                        model=model,
                        history=history,
                        incoming_dsl=json_to_dsl(incoming_json),
                        incoming_json=incoming_json,
                        seed=seed,
                        strict=False,
                        lenient=lenient,
                        side="?",
                        log_path=None,
                    )
                    return raw_dsl, dsl_line, payload, elapsed_dsl, "fallback-dsl"
                raise RelayError(
                    "structured relay failed at stage structured-json; automatic fallback disabled"
                ) from json_err

    raw, elapsed = _chat_once(client, model, working_history, seed=seed, response_format="json")
    payload, dsl = parse_structured_reply(raw)
    return raw, dsl, payload, elapsed, "structured-json"


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
) -> tuple[str, str, dict[str, Any], int]:
    prompt = (
        "Reply with exactly one ChoomLang DSL line.\n"
        f"Incoming DSL: {incoming_dsl}\n"
        f"Incoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    )
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]
    raw, elapsed_ms = _chat_once(client, model, working_history, seed=seed, response_format=None)

    try:
        payload = dsl_to_json_with_options(raw, lenient=lenient)
    except DSLParseError as exc:
        append_transcript(
            log_path,
            build_transcript_record(
                side=side,
                model=model,
                mode="dsl",
                request_mode="dsl",
                raw=raw,
                parsed=None,
                dsl=None,
                error=str(exc),
                retry=0,
                elapsed_ms=elapsed_ms,
                timeout_s=client.timeout,
                keep_alive_s=client.keep_alive,
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
        corrected, retry_elapsed_ms = _chat_once(
            client, model, correction_history, seed=seed, response_format=None
        )
        try:
            payload = dsl_to_json_with_options(corrected, lenient=lenient)
            return corrected, corrected, payload, elapsed_ms + retry_elapsed_ms
        except DSLParseError as retry_exc:
            append_transcript(
                log_path,
                build_transcript_record(
                    side=side,
                    model=model,
                    mode="dsl",
                    request_mode="dsl",
                    raw=corrected,
                    parsed=None,
                    dsl=None,
                    error=str(retry_exc),
                    retry=1,
                    elapsed_ms=retry_elapsed_ms,
                    timeout_s=client.timeout,
                    keep_alive_s=client.keep_alive,
                ),
            )
            raise RelayError(
                f"model failed strict ChoomLang validation after retry: {retry_exc}"
            ) from retry_exc

    return raw, raw, payload, elapsed_ms


def _chat_once(
    client: OllamaClient,
    model: str,
    history: list[dict[str, str]],
    *,
    seed: int | None,
    response_format: str | dict[str, Any] | None,
) -> tuple[str, int]:
    raw, elapsed_ms = client.chat(model, history, seed=seed, response_format=response_format)
    return _clip_model_output(raw), elapsed_ms


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
