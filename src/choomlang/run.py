"""Safe local execution skeleton for toolcall commands."""

from __future__ import annotations

from pathlib import Path

from .adapters import run_adapter
from .dsl import parse_dsl
from .errors import RunError


def run_toolcall(dsl_line: str, *, out_dir: str = "out", dry_run: bool = False) -> str:
    parsed = parse_dsl(dsl_line)
    if parsed.op != "toolcall" or parsed.target != "tool":
        raise RunError("choom run only supports canonical 'toolcall tool' commands")

    tool_name = str(parsed.params.get("name", ""))
    if not tool_name:
        raise RunError("toolcall requires param 'name' for adapter selection")

    params = {k: v for k, v in parsed.params.items() if k != "name"}
    out_path = Path(out_dir)

    # TODO(v0.9+): add configurable external adapters with explicit allowlists.
    return run_adapter(tool_name, params, out_path, dry_run)
