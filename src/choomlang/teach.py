"""Teach mode for token-by-token DSL explanations."""

from __future__ import annotations

from .dsl import ALIAS_TO_CANON, parse_dsl


def explain_dsl(line: str) -> str:
    parsed = parse_dsl(line)
    source_op = line.strip().split()[0]
    canonical = parsed.op
    alias_note = ""
    if source_op in ALIAS_TO_CANON:
        alias_note = f" (alias -> {canonical})"

    lines: list[str] = [
        "ChoomLang teach mode",
        f"- op: {source_op}{alias_note}",
        f"- target: {parsed.target}",
        f"- count: {parsed.count}",
    ]

    if parsed.params:
        lines.append("- params:")
        for key in sorted(parsed.params):
            value = parsed.params[key]
            lines.append(f"  - {key}: {value!r} ({type(value).__name__})")
    else:
        lines.append("- params: (none)")

    return "\n".join(lines)
