"""Script runner entrypoint for ``choom run``."""

from __future__ import annotations

from pathlib import Path

from .dsl import DSLParseError
from .protocol import iter_script_lines
from .run import RunError, run_toolcall


def run_script(
    script_path: str,
    *,
    workdir: str | None = None,
    resume: int | None = None,
    max_steps: int | None = None,
    dry_run: bool = False,
    timeout: float | None = None,
    keep_alive: float | None = None,
) -> list[str]:
    """Execute a .choom script line-by-line using built-in adapters.

    Args other than ``script_path``/``workdir``/``resume``/``max_steps``/``dry_run`` are
    accepted for CLI compatibility and future runtime expansion.
    """
    _ = timeout
    _ = keep_alive

    path = Path(script_path)
    if not path.exists() or not path.is_file():
        raise RunError(f"script file not found: {script_path}")

    if path.suffix != ".choom":
        raise RunError(f"script path must end with .choom: {script_path}")

    if resume is not None and resume < 1:
        raise RunError("--resume must be >= 1")
    if max_steps is not None and max_steps < 1:
        raise RunError("--max-steps must be >= 1")

    script_text = path.read_text(encoding="utf-8")
    filtered = iter_script_lines(script_text)

    start_idx = (resume - 1) if resume else 0
    selected = filtered[start_idx:]
    if max_steps is not None:
        selected = selected[:max_steps]

    out_dir_base = Path(workdir) if workdir else Path.cwd()
    out_dir = out_dir_base / "out"

    outputs: list[str] = []
    for line_number, line in selected:
        try:
            result = run_toolcall(line, out_dir=str(out_dir), dry_run=dry_run)
        except DSLParseError as exc:
            raise RunError(f"line {line_number}: parse error: {exc}") from exc
        except RunError as exc:
            raise RunError(f"line {line_number}: runtime error: {exc}") from exc
        outputs.append(f"line {line_number}: {result}")

    return outputs
