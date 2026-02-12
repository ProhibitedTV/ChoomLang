"""Stateful script runner for ``choom run``."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLMClient

from .dsl import DSLParseError, parse_dsl
from .adapters import run_adapter
from .errors import RunError
from .protocol import iter_script_lines

_INTERPOLATION_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_-]*)")


@dataclass(frozen=True)
class RunnerConfig:
    workdir: str | None = None
    dry_run: bool = False
    timeout: float | None = None
    keep_alive: float | None = None
    max_steps: int | None = None
    resume: int | bool | None = None
    llm_client: LLMClient | None = None
    a1111_url: str | None = None


@dataclass
class RunnerState:
    """Dictionary-backed runner state persisted as JSON."""

    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> RunnerState:
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RunError(f"state file must contain an object: {path}")
        return cls(data=payload)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self.data, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp_path.replace(path)


@dataclass
class StepResult:
    step: int
    dsl: str
    payload: dict[str, Any]
    status: str
    elapsed_ms: int
    output: Any = None
    stored_id: str | None = None
    error: str | None = None

    def to_transcript_record(self) -> dict[str, Any]:
        return {
            "ts": int(time.time() * 1000),
            "step": self.step,
            "dsl": self.dsl,
            "payload": self.payload,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "output": self.output,
            "stored_id": self.stored_id,
            "error": self.error,
        }


def run_script(
    script_path: str,
    *,
    workdir: str | None = None,
    resume: int | bool | None = None,
    max_steps: int | None = None,
    dry_run: bool = False,
    timeout: float | None = None,
    keep_alive: float | None = None,
    config: RunnerConfig | None = None,
    llm_client: LLMClient | None = None,
    a1111_url: str | None = None,
) -> list[str]:
    """Execute a .choom script line-by-line with persistent state + transcript."""
    cfg = config or RunnerConfig(
        workdir=workdir,
        dry_run=dry_run,
        timeout=timeout,
        keep_alive=keep_alive,
        max_steps=max_steps,
        resume=resume,
        llm_client=llm_client,
        a1111_url=a1111_url,
    )
    _ = cfg.timeout
    _ = cfg.keep_alive

    path = Path(script_path)
    if not path.exists() or not path.is_file():
        raise RunError(f"script file not found: {script_path}")
    if path.suffix != ".choom":
        raise RunError(f"script path must end with .choom: {script_path}")
    if isinstance(cfg.resume, int) and not isinstance(cfg.resume, bool) and cfg.resume < 1:
        raise RunError("--resume must be >= 1")
    if cfg.max_steps is not None and cfg.max_steps < 1:
        raise RunError("--max-steps must be >= 1")

    run_dir = Path(cfg.workdir) if cfg.workdir else Path.cwd()
    artifacts_dir = run_dir / "artifacts"
    state_path = run_dir / "state.json"
    transcript_path = run_dir / "transcript.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    state = RunnerState.load(state_path)
    if not state_path.exists():
        state.save_atomic(state_path)

    script_rows = iter_script_lines(path.read_text(encoding="utf-8"))
    start_idx = _determine_start_index(cfg.resume, transcript_path)
    selected = script_rows[start_idx:]
    if cfg.max_steps is not None:
        selected = selected[: cfg.max_steps]

    results: list[str] = []
    with transcript_path.open("a", encoding="utf-8") as transcript_file:
        for step_index, (line_number, dsl_line) in enumerate(selected, start=start_idx + 1):
            started = time.perf_counter()
            payload: dict[str, Any] | None = None
            try:
                payload = parse_dsl(dsl_line).to_json_dict()
                payload["params"] = _interpolate_params(payload["params"], state, cfg.dry_run)
                if payload["params"].get("__skip__"):
                    skip_message = str(payload["params"].pop("__skip__"))
                    step_result = StepResult(
                        step=step_index,
                        dsl=dsl_line,
                        payload=payload,
                        status="skipped",
                        elapsed_ms=_elapsed_ms(started),
                        output=None,
                        stored_id=None,
                        error=skip_message,
                    )
                    _append_transcript(transcript_file, step_result)
                    results.append(f"line {line_number}: skipped ({skip_message})")
                    continue

                output = _execute_payload(
                    payload,
                    artifacts_dir,
                    cfg.dry_run,
                    timeout=cfg.timeout,
                    keep_alive=cfg.keep_alive,
                    llm_client=cfg.llm_client,
                    step_index=step_index,
                    a1111_url=cfg.a1111_url,
                )
                stored_id = _store_output_if_requested(state, payload, output)
                state.save_atomic(state_path)

                step_result = StepResult(
                    step=step_index,
                    dsl=dsl_line,
                    payload=payload,
                    status="success",
                    elapsed_ms=_elapsed_ms(started),
                    output=output,
                    stored_id=stored_id,
                    error=None,
                )
                _append_transcript(transcript_file, step_result)
                results.append(f"line {line_number}: {output}")
            except DSLParseError as exc:
                step_result = StepResult(
                    step=step_index,
                    dsl=dsl_line,
                    payload=payload or {},
                    status="error",
                    elapsed_ms=_elapsed_ms(started),
                    output=None,
                    stored_id=None,
                    error=f"parse error: {exc}",
                )
                _append_transcript(transcript_file, step_result)
                raise RunError(f"line {line_number}: parse error: {exc}") from exc
            except RunError as exc:
                step_result = StepResult(
                    step=step_index,
                    dsl=dsl_line,
                    payload=payload or {},
                    status="error",
                    elapsed_ms=_elapsed_ms(started),
                    output=None,
                    stored_id=None,
                    error=str(exc),
                )
                _append_transcript(transcript_file, step_result)
                raise RunError(f"line {line_number}: runtime error: {exc}") from exc

    return results


def _determine_start_index(resume: int | bool | None, transcript_path: Path) -> int:
    if isinstance(resume, int) and not isinstance(resume, bool):
        return resume - 1
    if not resume:
        return 0
    return _count_completed_steps(transcript_path)


def _count_completed_steps(transcript_path: Path) -> int:
    if not transcript_path.exists():
        return 0
    completed = 0
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") in {"success", "skipped"}:
            completed += 1
    return completed


def _interpolate_params(params: dict[str, Any], state: RunnerState, dry_run: bool) -> dict[str, Any]:
    interpolated: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            try:
                interpolated[key] = _interpolate_string(value, state)
            except RunError as exc:
                if dry_run:
                    interpolated["__skip__"] = str(exc)
                    return interpolated
                raise
        else:
            interpolated[key] = value
    return interpolated


def _interpolate_string(value: str, state: RunnerState) -> str:
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in state:
            missing.append(key)
            return match.group(0)
        return str(state[key])

    rendered = _INTERPOLATION_RE.sub(_replace, value)
    if missing:
        unique = ", ".join(sorted(set(missing)))
        raise RunError(f"missing interpolation key(s): {unique}")
    return rendered


def _handle_gen_script_payload(payload: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    params = payload.get("params")
    if not isinstance(params, dict):
        raise RunError("runner requires params object for gen script")

    script_text = params.get("text")
    if script_text is None:
        script_text = params.get("script")
    if not isinstance(script_text, str):
        raise RunError("gen script requires params.text (or params.script) string output")

    stored_id = params.get("id")
    if isinstance(stored_id, str) and stored_id:
        destination = artifacts_dir / f"{stored_id}.choom"
        if not dry_run:
            destination.write_text(script_text, encoding="utf-8")
    return script_text


def _execute_payload(
    payload: dict[str, Any],
    artifacts_dir: Path,
    dry_run: bool,
    *,
    timeout: float | None = None,
    keep_alive: float | None = None,
    llm_client: LLMClient | None = None,
    step_index: int | None = None,
    a1111_url: str | None = None,
) -> str:
    if payload.get("op") == "gen" and payload.get("target") == "script":
        return _handle_gen_script_payload(payload, artifacts_dir, dry_run)

    if payload.get("op") != "toolcall" or payload.get("target") != "tool":
        raise RunError("runner requires canonical op='toolcall' and target='tool', or 'gen script'")

    params = payload.get("params")
    if not isinstance(params, dict):
        raise RunError("runner requires params object for toolcall")

    tool_name = params.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        raise RunError("runner requires params.name for toolcall adapter selection")

    adapter_params = {key: value for key, value in params.items() if key != "name"}
    context = {"step": step_index, "a1111_url": a1111_url}
    return run_adapter(
        tool_name,
        adapter_params,
        artifacts_dir,
        dry_run,
        timeout=timeout,
        keep_alive=keep_alive,
        llm_client=llm_client,
        context=context,
    )


def _store_output_if_requested(state: RunnerState, payload: dict[str, Any], output: Any) -> str | None:
    params = payload.get("params", {})
    if not isinstance(params, dict):
        return None
    stored_id = params.get("id")
    if not isinstance(stored_id, str) or not stored_id:
        return None
    state[stored_id] = output
    return stored_id


def _append_transcript(transcript_file: Any, step_result: StepResult) -> None:
    transcript_file.write(
        json.dumps(step_result.to_transcript_record(), sort_keys=True, separators=(",", ":")) + "\n"
    )
    transcript_file.flush()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
