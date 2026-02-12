"""Safe local execution skeleton for toolcall commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .dsl import parse_dsl


class RunError(ValueError):
    """Raised for runtime execution failures."""


Adapter = Callable[[dict[str, Any], Path, bool], str]


def _adapter_echo(params: dict[str, Any], out_dir: Path, dry_run: bool) -> str:
    _ = out_dir
    action = "dry-run" if dry_run else "executed"
    return f"echo {action}: {json.dumps(params, sort_keys=True)}"


def _safe_join(base: Path, user_path: str) -> Path:
    candidate = (base / user_path).resolve()
    base_resolved = base.resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise RunError(f"unsafe path outside output directory: {user_path}")
    return candidate


def _adapter_write_file(params: dict[str, Any], out_dir: Path, dry_run: bool) -> str:
    rel = str(params.get("path", ""))
    if not rel:
        raise RunError("write_file requires param 'path'")
    text = str(params.get("text", ""))
    destination = _safe_join(out_dir, rel)
    if dry_run:
        return f"write_file dry-run: {destination} ({len(text)} chars)"

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return f"write_file executed: {destination}"


BUILTIN_ADAPTERS: dict[str, Adapter] = {
    "echo": _adapter_echo,
    "write_file": _adapter_write_file,
}


def run_toolcall(dsl_line: str, *, out_dir: str = "out", dry_run: bool = False) -> str:
    parsed = parse_dsl(dsl_line)
    if parsed.op != "toolcall" or parsed.target != "tool":
        raise RunError("choom run only supports canonical 'toolcall tool' commands")

    tool_name = str(parsed.params.get("name", ""))
    if not tool_name:
        raise RunError("toolcall requires param 'name' for adapter selection")

    adapter = BUILTIN_ADAPTERS.get(tool_name)
    if adapter is None:
        known = ", ".join(sorted(BUILTIN_ADAPTERS))
        raise RunError(f"unknown tool adapter '{tool_name}'. known adapters: {known}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # TODO(v0.9+): add configurable external adapters with explicit allowlists.
    return adapter(parsed.params, out_path, dry_run)
