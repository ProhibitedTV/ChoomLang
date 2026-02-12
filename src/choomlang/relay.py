from __future__ import annotations

import json
import statistics
import sys
from difflib import get_close_matches
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal
from urllib import error, request

from .dsl import DSLParseError
from .protocol import build_contract_prompt, build_guard_prompt, canonical_json_schema, parse_script_text
from .registry import CANONICAL_OPS, CANONICAL_TARGETS, normalize_op, validate_payload
from .translate import json_to_dsl

OLLAMA_URL = "http://localhost:11434"
MAX_MESSAGE_CHARS = 4000
PING_PAYLOAD = {"op": "healthcheck", "target": "txt", "count": 1, "params": {}}
RequestMode = Literal["dsl", "structured-schema", "structured-json", "fallback-dsl"]


def _extract_model_names(tags_payload: dict[str, Any]) -> list[str]:
    models = tags_payload.get("models", [])
    names: list[str] = []
    if isinstance(models, list):
        for model in models:
            if not isinstance(model, dict):
                continue
            name = model.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def suggest_model_names(name: str, available: list[str], *, limit: int = 3) -> list[str]:
    if not available:
        return []
    return get_close_matches(name, available, n=limit, cutoff=0.4)


def _format_structured_failure(stage: str, error: RelayError) -> RelayError:
    last_raw = error.raw_response or "<none>"
    hint = "try --no-schema; check model names from `ollama list`"
    return RelayError(
        f"structured relay failed in mode {stage}; reason={error}; "
        f"last raw assistant content={last_raw}; suggested fix: {hint}",
        http_status=error.http_status,
        raw_response=error.raw_response,
        stage=stage,
    )

class RelayError(RuntimeError):
    """Raised when relay execution fails."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        raw_response: str | None = None,
        reason: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.raw_response = raw_response
        self.reason = reason
        self.stage = stage


def build_ping_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": (
                "Return JSON only with no extra text. "
                f"Reply exactly with: {json.dumps(PING_PAYLOAD, sort_keys=True)}"
            ),
        }
    ]


def build_chat_request(
    *,
    model: str,
    messages: list[dict[str, str]],
    seed: int | None = None,
    response_format: str | dict[str, Any] | None = None,
    keep_alive: float | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
    if seed is not None:
        payload["options"] = {"seed": seed}
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if response_format is not None:
        payload["format"] = response_format
    return payload


def call_ollama_chat(
    client: "OllamaClient",
    *,
    model: str,
    messages: list[dict[str, str]],
    seed: int | None,
    response_format: str | dict[str, Any] | None,
    timeout: float,
    keep_alive: float | None,
) -> tuple[str, int, int]:
    payload = build_chat_request(
        model=model,
        messages=messages,
        seed=seed,
        response_format=response_format,
        keep_alive=keep_alive,
        stream=False,
    )
    data, elapsed_ms, status = client.post_json("/api/chat", payload, timeout=timeout)
    content = data.get("message", {}).get("content")
    if not isinstance(content, str):
        raise RelayError(
            "Ollama returned an unexpected /api/chat response shape",
            http_status=status,
            raw_response=json.dumps(data, sort_keys=True),
        )
    return content, elapsed_ms, status


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

    def get_tags(self, *, timeout: float | None = None) -> tuple[dict[str, Any], int, int]:
        req = request.Request(f"{self.base_url}/api/tags", method="GET")
        started = perf_counter()
        use_timeout = self.timeout if timeout is None else timeout
        try:
            with request.urlopen(req, timeout=use_timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = int(getattr(resp, "status", 200))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RelayError(
                f"Ollama request failed (/api/tags): HTTP {exc.code} {detail}",
                http_status=exc.code,
                raw_response=detail,
                stage="probe-tags",
                reason="http-error",
            ) from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                raise RelayError(
                    f"Ollama request timed out after {use_timeout:g}s",
                    reason="timeout",
                    stage="probe-tags",
                ) from exc
            raise RelayError(
                f"Could not connect to Ollama at {self.base_url}. Is ollama running?",
                reason="connect-error",
                stage="probe-tags",
            ) from exc
        except TimeoutError as exc:
            raise RelayError(
                f"Ollama request timed out after {use_timeout:g}s",
                reason="timeout",
                stage="probe-tags",
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RelayError("Ollama returned non-JSON output", stage="probe-tags") from exc
        if not isinstance(data, dict):
            raise RelayError("Ollama returned a non-object JSON payload", stage="probe-tags")
        return data, int((perf_counter() - started) * 1000), status

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        seed: int | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> tuple[str, int, int]:
        try:
            return call_ollama_chat(
                self,
                model=model,
                messages=messages,
                seed=seed,
                response_format=response_format,
                timeout=self.timeout,
                keep_alive=self.keep_alive,
            )
        except RelayError as exc:
            if exc.http_status == 404:
                available: list[str] = []
                try:
                    tags, _, _ = self.get_tags(timeout=self.timeout)
                    available = _extract_model_names(tags)
                except RelayError:
                    available = []
                suggestions = suggest_model_names(model, available)
                if suggestions:
                    raise RelayError(
                        f"model '{model}' not found. Closest matches from ollama list: {', '.join(suggestions)}",
                        http_status=exc.http_status,
                        raw_response=exc.raw_response,
                        stage=exc.stage,
                        reason="model-not-found",
                    ) from exc
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

        data, elapsed_ms, status = self.post_json("/api/generate", gen_payload)
        content = data.get("response")
        if not isinstance(content, str):
            raise RelayError("Ollama returned an unexpected response shape", http_status=status)
        return content, elapsed_ms, status

    def post_json(
        self, path: str, payload: dict[str, Any], *, timeout: float | None = None
    ) -> tuple[dict[str, Any], int, int]:
        return self._post_json(path, payload, timeout=timeout)

    def _post_json(
        self, path: str, payload: dict[str, Any], *, timeout: float | None = None
    ) -> tuple[dict[str, Any], int, int]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = perf_counter()
        use_timeout = self.timeout if timeout is None else timeout
        try:
            with request.urlopen(req, timeout=use_timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = int(getattr(resp, "status", 200))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RelayError(
                f"Ollama request failed ({path}): HTTP {exc.code} {detail}",
                http_status=exc.code,
                raw_response=detail,
                reason="http-error",
            ) from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                raise RelayError(
                    f"Ollama request timed out after {use_timeout:g}s",
                    reason="timeout",
                ) from exc
            raise RelayError(
                f"Could not connect to Ollama at {self.base_url}. Is ollama running?",
                reason="connect-error",
            ) from exc
        except TimeoutError as exc:
            raise RelayError(
                f"Ollama request timed out after {use_timeout:g}s",
                reason="timeout",
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RelayError("Ollama returned non-JSON output", raw_response=raw) from exc
        if not isinstance(data, dict):
            raise RelayError("Ollama returned a non-object JSON payload", raw_response=raw)
        return data, int((perf_counter() - started) * 1000), status


def run_probe(*, client: OllamaClient, models: list[str]) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    ok = True
    try:
        _, elapsed_ms, status = client.get_tags(timeout=client.timeout)
        results.append({"kind": "tags", "ok": status == 200, "http_status": status, "elapsed_ms": elapsed_ms})
        if status != 200:
            ok = False
    except RelayError as exc:
        results.append(
            {
                "kind": "tags",
                "ok": False,
                "http_status": exc.http_status,
                "elapsed_ms": None,
                "reason": str(exc),
            }
        )
        return False, results

    for model in models:
        try:
            raw, elapsed_ms, status = call_ollama_chat(
                client,
                model=model,
                messages=build_ping_messages(),
                seed=None,
                response_format="json",
                timeout=client.timeout,
                keep_alive=client.keep_alive,
            )
            parse_structured_reply(raw)
            results.append(
                {
                    "kind": "model",
                    "model": model,
                    "ok": True,
                    "http_status": status,
                    "elapsed_ms": elapsed_ms,
                }
            )
        except RelayError as exc:
            ok = False
            results.append(
                {
                    "kind": "model",
                    "model": model,
                    "ok": False,
                    "http_status": exc.http_status,
                    "elapsed_ms": None,
                    "reason": str(exc),
                }
            )
    return ok, results


def warm_models(*, client: OllamaClient, models: list[str]) -> list[dict[str, Any]]:
    _, results = run_probe(client=client, models=models)
    return [r for r in results if r.get("kind") == "model"]


def strict_validate_with_retry(
    message: str,
    *,
    strict: bool,
    lenient: bool = False,
    retry: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any]]:
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


def parse_structured_reply(
    raw: str,
    *,
    strict_ops: bool = True,
    strict_targets: bool = True,
) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RelayError("structured relay response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RelayError("structured relay response must be a JSON object")

    normalized = {
        "op": payload.get("op"),
        "target": payload.get("target"),
        "count": payload.get("count", 1),
        "params": payload.get("params", {}),
    }

    try:
        validate_payload(
            normalized,
            strict_ops=strict_ops,
            strict_targets=strict_targets,
        )
    except ValueError as exc:
        message = str(exc)
        suggestion = "use --allow-unknown-op/--allow-unknown-target or try --no-schema"
        if "field op" in message:
            bad = normalized.get("op")
            if isinstance(bad, str):
                candidate = normalize_op(bad)
                if candidate in CANONICAL_OPS and candidate != bad:
                    suggestion = f"alias detected: try canonical op '{candidate}' or use --allow-unknown-op"
                else:
                    suggestion = f"use canonical ops {sorted(CANONICAL_OPS)} or --allow-unknown-op; try --no-schema"
        elif "field target" in message:
            suggestion = f"use canonical targets {sorted(CANONICAL_TARGETS)} or --allow-unknown-target; try --no-schema"
        invalid_fields: list[str] = []
        if "field op" in message:
            invalid_fields.append("op")
        if "field target" in message:
            invalid_fields.append("target")
        if "field count" in message:
            invalid_fields.append("count")
        if "field params" in message:
            invalid_fields.append("params")
        raise RelayError(
            f"structured relay validation failed: {message}; suggested fix: {suggestion}",
            raw_response=raw,
            reason=",".join(invalid_fields) if invalid_fields else None,
            stage="structured-validation",
        ) from exc

    normalized["op"] = normalize_op(str(normalized["op"]))
    normalized["target"] = str(normalized["target"])
    normalized["count"] = int(normalized["count"])
    normalized["params"] = dict(normalized["params"])

    if normalized["op"] == "gen" and normalized["target"] == "script":
        params = normalized["params"]
        script_text = params.get("text")
        if not isinstance(script_text, str):
            raise RelayError(
                "structured relay validation failed: field params.text is required string when op='gen' and target='script'; suggested fix: include generated script in params.text (not prompt)",
                raw_response=raw,
                reason="params",
                stage="structured-validation",
            )
        if "prompt" in params:
            raise RelayError(
                "structured relay validation failed: field params.prompt is not allowed when op='gen' and target='script'; suggested fix: emit script in params.text",
                raw_response=raw,
                reason="params",
                stage="structured-validation",
            )
        try:
            parse_script_text(script_text)
        except DSLParseError as exc:
            raise RelayError(
                f"structured relay validation failed: params.text must be a valid multi-line ChoomLang script ({exc}); suggested fix: emit parseable script lines in params.text",
                raw_response=raw,
                reason="params",
                stage="structured-validation",
            ) from exc

    dsl = json_to_dsl(normalized)
    return normalized, dsl


def decide_structured_recovery(
    *,
    schema_failed: bool,
    json_failed: bool,
    strict: bool,
    fallback_enabled: bool,
) -> str:
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
    request_id: int,
    stage: RequestMode,
    http_status: int | None,
    fallback_reason: str | None,
    invalid_fields: list[str] | None = None,
    raw_json_text: str | None = None,
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "side": side,
        "model": model,
        "mode": mode,
        "stage": stage,
        "request_mode": request_mode,
        "http_status": http_status,
        "raw": raw,
        "parsed": parsed,
        "dsl": dsl,
        "error": error,
        "retry": retry,
        "elapsed_ms": elapsed_ms,
        "timeout_s": timeout_s,
        "keep_alive_s": keep_alive_s,
        "fallback_reason": fallback_reason,
        "invalid_fields": invalid_fields,
        "raw_json_text": raw_json_text,
    }


def summarize_transcript(records: list[dict[str, Any]]) -> dict[str, Any]:
    stage_groups: dict[str, list[int]] = {}
    fallback_counts: dict[str, int] = {}
    for record in records:
        stage = str(record.get("stage", "unknown"))
        elapsed = record.get("elapsed_ms")
        if isinstance(elapsed, int):
            stage_groups.setdefault(stage, []).append(elapsed)
        reason = record.get("fallback_reason")
        if reason:
            fallback_counts[stage] = fallback_counts.get(stage, 0) + 1

    stage_latency: dict[str, dict[str, float]] = {}
    for stage, values in stage_groups.items():
        if values:
            stage_latency[stage] = {
                "avg_ms": round(sum(values) / len(values), 2),
                "median_ms": float(statistics.median(values)),
            }

    return {
        "total_turns": len(records),
        "retries": sum(int(record.get("retry", 0)) for record in records),
        "fallbacks_by_stage": dict(sorted(fallback_counts.items())),
        "elapsed_ms_by_stage": dict(sorted(stage_latency.items())),
    }


def print_relay_summary(summary: dict[str, Any], *, log_path: str | None) -> None:
    print(
        "relay summary: "
        f"turns={summary['total_turns']} retries={summary['retries']} "
        f"fallbacks={json.dumps(summary['fallbacks_by_stage'], sort_keys=True)}",
        file=sys.stderr,
    )
    for stage, values in summary["elapsed_ms_by_stage"].items():
        print(
            f"  {stage}: avg={values['avg_ms']}ms median={values['median_ms']}ms",
            file=sys.stderr,
        )
    if log_path:
        print(f"  transcript: {log_path}", file=sys.stderr)


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
    allow_unknown_op: bool = False,
    allow_unknown_target: bool = False,
    fallback_enabled: bool = True,
    use_contract_in_structured: bool = True,
    raw_json: bool = False,
    log_path: str | None = None,
    lenient: bool = False,
    warm: bool = False,
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    if turns < 1:
        raise RelayError("turns must be >= 1")

    if warm:
        warm_models(client=client, models=[a_model, b_model])

    if not structured:
        contract = build_contract_prompt("dsl")
        if system_a is None:
            system_a = contract
        if system_b is None:
            system_b = contract

    transcript: list[tuple[str, str, dict[str, Any], str | None]] = []
    records: list[dict[str, Any]] = []
    request_id = 0
    histories = {"A": _new_history(system_a), "B": _new_history(system_b)}

    current = start or "ping tool service=relay"
    _, current_json = strict_validate_with_retry(current, strict=True, lenient=lenient)

    for _ in range(turns):
        for speaker, model, other in (("A", a_model, "B"), ("B", b_model, "A")):
            request_id += 1
            fallback_reason = None
            if structured:
                (
                    response_raw,
                    response,
                    response_json,
                    elapsed_ms,
                    request_mode,
                    http_status,
                    retry_value,
                    fallback_reason,
                ) = _structured_model_step(
                    client=client,
                    model=model,
                    history=histories[speaker],
                    incoming_json=current_json,
                    seed=seed,
                    use_schema=use_schema,
                    strict=strict,
                    allow_unknown_op=allow_unknown_op,
                    allow_unknown_target=allow_unknown_target,
                    fallback_enabled=fallback_enabled,
                    lenient=lenient,
                    add_contract=use_contract_in_structured,
                )
                mode = "structured"
                next_incoming = json.dumps(response_json, sort_keys=True)
            else:
                response_raw, response, response_json, elapsed_ms, http_status, retry_value = _dsl_model_step(
                    client=client,
                    model=model,
                    history=histories[speaker],
                    incoming_dsl=current,
                    incoming_json=current_json,
                    seed=seed,
                    strict=strict,
                    lenient=lenient,
                )
                mode = "dsl"
                request_mode = "dsl"
                next_incoming = response

            _append_exchange(histories[speaker], current, next_incoming)
            _append_exchange(histories[other], current, next_incoming)
            transcript.append((speaker, response, response_json, response_raw if raw_json else None))

            record = build_transcript_record(
                request_id=request_id,
                side=speaker,
                model=model,
                mode=mode,
                stage=request_mode,
                request_mode=request_mode,
                http_status=http_status,
                raw=response_raw,
                parsed=response_json,
                dsl=response,
                error=None,
                retry=retry_value,
                elapsed_ms=elapsed_ms,
                timeout_s=client.timeout,
                keep_alive_s=client.keep_alive,
                fallback_reason=fallback_reason,
                invalid_fields=None,
                raw_json_text=response_raw if structured else None,
            )
            records.append(record)
            append_transcript(log_path, record)

            current = next_incoming if structured else response
            current_json = response_json

    print_relay_summary(summarize_transcript(records), log_path=log_path)
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
    allow_unknown_op: bool,
    allow_unknown_target: bool,
    fallback_enabled: bool,
    lenient: bool,
    add_contract: bool,
) -> tuple[str, str, dict[str, Any], int, RequestMode, int | None, int, str | None]:
    contract = build_contract_prompt("structured") if add_contract else ""
    prompt = (
        "Reply with exactly one canonical ChoomLang JSON object and no extra text.\n"
        f"{contract}\nIncoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    ).strip()
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]

    if use_schema:
        schema_mode = "strict" if strict else "permissive"
        try:
            raw_schema, elapsed_schema, status_schema = _chat_once(
                client, model, working_history, seed=seed, response_format=canonical_json_schema(mode=schema_mode)
            )
            payload, dsl = parse_structured_reply(
                raw_schema,
                strict_ops=not allow_unknown_op,
                strict_targets=not allow_unknown_target,
            )
            return raw_schema, dsl, payload, elapsed_schema, "structured-schema", status_schema, 0, None
        except RelayError as schema_err:
            reason = f"schema-failed:{schema_err}"
            decision = decide_structured_recovery(
                schema_failed=True,
                json_failed=False,
                strict=strict,
                fallback_enabled=fallback_enabled,
            )
            if decision == "fail-no-fallback":
                raise RelayError(
                    f"structured schema stage failed: {schema_err}",
                    http_status=schema_err.http_status,
                    raw_response=schema_err.raw_response,
                    stage="structured-schema",
                ) from schema_err
            print(
                f"warning: structured schema stage failed ({schema_err}); retrying with format=json",
                file=sys.stderr,
            )
            try:
                raw_json, elapsed_json, status_json = _chat_once(
                    client, model, working_history, seed=seed, response_format="json"
                )
                payload, dsl = parse_structured_reply(
                    raw_json,
                    strict_ops=not allow_unknown_op,
                    strict_targets=not allow_unknown_target,
                )
                return (
                    raw_json,
                    dsl,
                    payload,
                    elapsed_json,
                    "structured-json",
                    status_json,
                    1,
                    reason,
                )
            except RelayError as json_err:
                if strict:
                    raise _format_structured_failure("structured-json", json_err) from json_err
                if not fallback_enabled:
                    wrapped = _format_structured_failure("structured-json", json_err)
                    raise RelayError(
                        f"{wrapped}; automatic fallback disabled",
                        http_status=wrapped.http_status,
                        raw_response=wrapped.raw_response,
                        stage=wrapped.stage,
                    ) from json_err
                print("warning: structured json stage failed; falling back to DSL guard mode", file=sys.stderr)
                raw_dsl, dsl_line, payload, elapsed_dsl, http_status, retry_count = _dsl_model_step(
                    client=client,
                    model=model,
                    history=history,
                    incoming_dsl=json_to_dsl(incoming_json),
                    incoming_json=incoming_json,
                    seed=seed,
                    strict=False,
                    lenient=lenient,
                )
                return (
                    raw_dsl,
                    dsl_line,
                    payload,
                    elapsed_dsl,
                    "fallback-dsl",
                    http_status,
                    retry_count,
                    f"{reason};json-failed:{json_err}",
                )

    raw, elapsed, status = _chat_once(client, model, working_history, seed=seed, response_format=canonical_json_schema(mode="permissive"))
    payload, dsl = parse_structured_reply(
        raw,
        strict_ops=not allow_unknown_op,
        strict_targets=not allow_unknown_target,
    )
    return raw, dsl, payload, elapsed, "structured-json", status, 0, None


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
) -> tuple[str, str, dict[str, Any], int, int | None, int]:
    prompt = (
        "Reply with exactly one ChoomLang DSL line.\n"
        f"Incoming DSL: {incoming_dsl}\n"
        f"Incoming JSON: {json.dumps(incoming_json, sort_keys=True)}"
    )
    if len(prompt) > MAX_MESSAGE_CHARS:
        raise RelayError("incoming message too large to relay")

    working_history = [*history, {"role": "user", "content": prompt}]
    raw, elapsed_ms, http_status = _chat_once(client, model, working_history, seed=seed, response_format=None)

    try:
        payload = dsl_to_json_with_options(raw, lenient=lenient)
    except DSLParseError as exc:
        if not strict:
            raise

        correction_prompt = build_guard_prompt(error=str(exc), previous=raw)
        correction_history = [
            *working_history,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": correction_prompt},
        ]
        corrected, retry_elapsed_ms, retry_status = _chat_once(
            client, model, correction_history, seed=seed, response_format=None
        )
        try:
            payload = dsl_to_json_with_options(corrected, lenient=lenient)
            return corrected, corrected, payload, elapsed_ms + retry_elapsed_ms, retry_status, 1
        except DSLParseError as retry_exc:
            raise RelayError(
                f"model failed strict ChoomLang validation after retry: {retry_exc}",
                stage="dsl",
            ) from retry_exc

    return raw, raw, payload, elapsed_ms, http_status, 0


def _chat_once(
    client: OllamaClient,
    model: str,
    history: list[dict[str, str]],
    *,
    seed: int | None,
    response_format: str | dict[str, Any] | None,
) -> tuple[str, int, int | None]:
    raw, elapsed_ms, status = client.chat(model, history, seed=seed, response_format=response_format)
    return _clip_model_output(raw), elapsed_ms, status


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
