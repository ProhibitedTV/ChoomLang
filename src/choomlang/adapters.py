"""Built-in tool adapters and registry helpers."""

from __future__ import annotations

import json
import base64
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib import request, error

from .errors import RunError
from .llm import LLMClient, OllamaLLMClient

Adapter = Callable[[dict[str, Any], Path, bool, float | None, float | None, LLMClient, dict[str, Any] | None], str]


def _validate_relative_artifact_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if not raw_path:
        raise RunError("adapter path must not be empty")
    if path.is_absolute():
        raise RunError(f"unsafe artifact path (absolute paths are not allowed): {raw_path}")
    if ".." in path.parts:
        raise RunError(f"unsafe artifact path (path traversal is not allowed): {raw_path}")
    return path


def resolve_artifact_path(base_dir: Path, raw_path: str) -> tuple[Path, str]:
    rel_path = _validate_relative_artifact_path(raw_path)
    resolved = (base_dir / rel_path).resolve()
    base_resolved = base_dir.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise RunError(f"unsafe artifact path (must stay within artifacts): {raw_path}")
    return resolved, rel_path.as_posix()


def _adapter_echo(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = artifacts_dir
    _ = dry_run
    _ = context
    _ = timeout
    _ = keep_alive
    _ = llm_client
    return json.dumps(params, sort_keys=True)


def _adapter_write_file(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = timeout
    _ = keep_alive
    _ = llm_client
    _ = context
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("write_file requires param 'path'")
    text = str(params.get("text", ""))
    destination, relative = resolve_artifact_path(artifacts_dir, raw_path)
    if dry_run:
        return relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return relative


def _adapter_read_file(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = dry_run
    _ = timeout
    _ = keep_alive
    _ = llm_client
    _ = context
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("read_file requires param 'path'")
    destination, _ = resolve_artifact_path(artifacts_dir, raw_path)
    if not destination.exists() or not destination.is_file():
        raise RunError(f"read_file path does not exist or is not a file: {raw_path}")
    return destination.read_text(encoding="utf-8")


def _adapter_mkdir(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = timeout
    _ = keep_alive
    _ = llm_client
    _ = context
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("mkdir requires param 'path'")
    destination, relative = resolve_artifact_path(artifacts_dir, raw_path)
    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)
    return relative


def _adapter_list_dir(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = dry_run
    _ = timeout
    _ = keep_alive
    _ = llm_client
    _ = context
    raw_path = str(params.get("path", "."))
    destination, _ = resolve_artifact_path(artifacts_dir, raw_path)
    if not destination.exists() or not destination.is_dir():
        raise RunError(f"list_dir path does not exist or is not a directory: {raw_path}")
    entries = sorted(item.name for item in destination.iterdir())
    return json.dumps(entries, separators=(",", ":"))


def _adapter_ollama_chat(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = artifacts_dir
    _ = dry_run
    _ = context
    model = params.get("model")
    if not isinstance(model, str) or not model:
        raise RunError("ollama_chat requires param 'model'")
    prompt = params.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        prompt = str(prompt)
    messages = params.get("messages")
    normalized_messages: list[dict[str, str]] | None = None
    if messages is not None:
        if isinstance(messages, str):
            candidate = messages.strip()
            if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"\"", "'"}:
                candidate = candidate[1:-1]
            try:
                messages_obj = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise RunError("ollama_chat param 'messages' must be valid JSON") from exc
        else:
            messages_obj = messages
        if not isinstance(messages_obj, list) or not messages_obj:
            raise RunError("ollama_chat param 'messages' must be a non-empty list")
        normalized_messages = []
        for item in messages_obj:
            if not isinstance(item, dict):
                raise RunError("ollama_chat messages entries must be objects")
            role = item.get("role")
            content = item.get("content")
            if not isinstance(role, str) or not isinstance(content, str):
                raise RunError("ollama_chat messages require string role/content")
            normalized_messages.append({"role": role, "content": content})
    return llm_client.chat(
        model,
        prompt=prompt,
        messages=normalized_messages,
        timeout=timeout,
        keep_alive=keep_alive,
    )


def _as_int(params: dict[str, Any], key: str) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RunError(f"a1111_txt2img param '{key}' must be an integer") from exc


def _a1111_should_retry(exc: Exception) -> bool:
    if isinstance(exc, error.HTTPError):
        return 500 <= exc.code < 600
    if isinstance(exc, error.URLError):
        return True
    reset_markers = (
        "connection reset",
        "connection aborted",
        "broken pipe",
        "temporarily unavailable",
    )
    return any(marker in str(exc).lower() for marker in reset_markers)


def _a1111_interrupt(base_url: str, timeout: float | None) -> bool:
    endpoint = base_url.rstrip("/") + "/sdapi/v1/interrupt"
    req = request.Request(endpoint, data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _adapter_a1111_txt2img(
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    timeout: float | None,
    keep_alive: float | None,
    llm_client: LLMClient,
    context: dict[str, Any] | None = None,
) -> str:
    _ = keep_alive
    _ = llm_client

    base_url: str | None = None
    if isinstance(params.get("base_url"), str) and params["base_url"]:
        base_url = params["base_url"]
    if base_url is None and isinstance(context, dict):
        context_base_url = context.get("a1111_url") or context.get("base_url")
        if isinstance(context_base_url, str) and context_base_url:
            base_url = context_base_url
    legacy_context = params.get("context")
    if base_url is None and isinstance(legacy_context, dict):
        legacy_base_url = legacy_context.get("base_url")
        if isinstance(legacy_base_url, str) and legacy_base_url:
            base_url = legacy_base_url
    if base_url is None:
        base_url = "http://127.0.0.1:7860"

    request_timeout = timeout
    if isinstance(context, dict) and context.get("a1111_timeout") is not None:
        request_timeout = context.get("a1111_timeout")
    if "timeout" in params and params.get("timeout") is not None:
        request_timeout = params.get("timeout")
    if request_timeout is not None:
        try:
            request_timeout = float(request_timeout)
        except (TypeError, ValueError) as exc:
            raise RunError("a1111_txt2img timeout must be numeric") from exc

    cancel_on_timeout = False
    if isinstance(context, dict):
        cancel_on_timeout = bool(context.get("cancel_on_timeout", False))
    if "cancel_on_timeout" in params:
        cancel_on_timeout = bool(params.get("cancel_on_timeout"))

    seed_value = _as_int(params, "seed")

    payload: dict[str, Any] = {}
    for key in ("prompt",):
        if key in params:
            payload[key] = params[key]
    if "negative" in params:
        payload["negative_prompt"] = params["negative"]
    if "cfg" in params:
        payload["cfg_scale"] = params["cfg"]
    if "sampler" in params:
        payload["sampler_name"] = params["sampler"]
    for key in ("width", "height", "steps", "seed"):
        int_value = _as_int(params, key)
        if int_value is not None:
            payload[key] = int_value
    if "n" in params:
        batch_size = _as_int(params, "n")
        if batch_size is None or batch_size < 1:
            raise RunError("a1111_txt2img param 'n' must be an integer >= 1")
        payload["batch_size"] = batch_size

    if dry_run:
        return json.dumps([], separators=(",", ":"))

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    endpoint = base_url.rstrip("/") + "/sdapi/v1/txt2img"
    req = request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    response_body: bytes | None = None
    attempts = 3
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with request.urlopen(req, timeout=request_timeout) as resp:
                response_body = resp.read()
            break
        except TimeoutError as exc:
            if cancel_on_timeout:
                interrupted = _a1111_interrupt(base_url, request_timeout)
                print(
                    f"a1111_txt2img timeout; interrupt {'succeeded' if interrupted else 'failed'}",
                    flush=True,
                )
            raise RunError(f"a1111_txt2img request timed out after {request_timeout}s") from exc
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _a1111_should_retry(exc):
                print(f"a1111_txt2img transient error (attempt {attempt}/{attempts}): {exc}; retrying", flush=True)
                import time
                time.sleep(0.2 * attempt)
                continue
            raise RunError(f"a1111_txt2img request failed: {exc}") from exc
    if response_body is None:
        raise RunError(f"a1111_txt2img request failed: {last_exc}")

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RunError("a1111_txt2img response was not valid JSON") from exc

    images = response_json.get("images") if isinstance(response_json, dict) else None
    if not isinstance(images, list) or not all(isinstance(item, str) for item in images):
        raise RunError("a1111_txt2img response must include an 'images' list of base64 strings")

    seed_suffix = "x" if seed_value in (None, -1) else str(seed_value)
    step_value = _as_int(params, "step")
    if step_value is None and isinstance(context, dict):
        try:
            step_value = int(context.get("step")) if context.get("step") is not None else None
        except (TypeError, ValueError) as exc:
            raise RunError("a1111_txt2img context step must be an integer") from exc
    if step_value is None:
        step_value = 1

    output_paths: list[str] = []
    for idx, encoded in enumerate(images, start=1):
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise RunError("a1111_txt2img response contained invalid base64 image data") from exc
        filename = f"a1111_txt2img_{step_value:04d}_{idx:02d}_seed{seed_suffix}.png"
        destination, relative = resolve_artifact_path(artifacts_dir, filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(image_bytes)
        output_paths.append(relative)

    return json.dumps(output_paths, separators=(",", ":"))



BUILTIN_ADAPTERS: dict[str, Adapter] = {
    "echo": _adapter_echo,
    "list_dir": _adapter_list_dir,
    "mkdir": _adapter_mkdir,
    "read_file": _adapter_read_file,
    "write_file": _adapter_write_file,
    "ollama": _adapter_ollama_chat,
    "ollama_chat": _adapter_ollama_chat,
    "a1111_txt2img": _adapter_a1111_txt2img,
}


def run_adapter(
    name: str,
    params: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    *,
    timeout: float | None = None,
    keep_alive: float | None = None,
    llm_client: LLMClient | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    adapter = BUILTIN_ADAPTERS.get(name)
    if adapter is None:
        known = ", ".join(sorted(BUILTIN_ADAPTERS))
        raise RunError(f"unknown tool adapter '{name}'. known adapters: {known}")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return adapter(params, artifacts_dir, dry_run, timeout, keep_alive, llm_client or OllamaLLMClient(), context)
