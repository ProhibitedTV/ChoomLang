"""Protocol-focused helpers added in ChoomLang v0.3."""

from __future__ import annotations

from .dsl import DSLParseError, format_dsl, parse_dsl

KNOWN_OPS = ["gen", "classify", "summarize", "plan", "healthcheck", "toolcall", "forward"]
KNOWN_TARGETS = ["img", "txt", "aud", "vid", "vec", "tool"]


def strip_inline_comment(line: str) -> str:
    """Strip comments that start with unquoted '#'."""
    in_quote = False
    escape = False
    for i, ch in enumerate(line):
        if in_quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_quote = False
            continue

        if ch == '"':
            in_quote = True
            continue

        if ch == "#":
            return line[:i].rstrip()

    return line.rstrip()


def iter_script_lines(text: str) -> list[tuple[int, str]]:
    """Return parseable script lines as (line_number, dsl_text)."""
    rows: list[tuple[int, str]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        without_comment = strip_inline_comment(raw).strip()
        if not without_comment:
            continue
        rows.append((line_number, without_comment))
    return rows


def build_guard_prompt(error: str | None = None, previous: str | None = None) -> str:
    base = (
        "Reply with exactly one valid ChoomLang DSL line and no extra text. "
        "Grammar: <op> <target>[count] key=value ... "
        "Bans: no JSON, no trailing punctuation, no standalone symbols. "
        "Examples: ping txt; gen txt prompt=\"hello\"; "
        "classify txt sentiment=polarity; toolcall tool[1] name=search query=\"cats\"."
    )
    if error is None and previous is None:
        return base

    parts = [base]
    if error:
        parts.append(f"Error: {error}")
    if previous:
        parts.append(f"Previous reply: {previous!r}")
    return " ".join(parts)


def canonical_json_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ChoomLang canonical payload",
        "type": "object",
        "required": ["op", "target", "count", "params"],
        "additionalProperties": False,
        "properties": {
            "op": {
                "anyOf": [{"$ref": "#/$defs/knownOp"}, {"type": "string"}],
                "description": "Canonical operation name. Known ops are enumerated but extensions are allowed.",
            },
            "target": {
                "anyOf": [{"$ref": "#/$defs/knownTarget"}, {"type": "string"}],
                "description": "Target domain. Known targets are enumerated but extensions are allowed.",
            },
            "count": {"type": "integer", "minimum": 1, "default": 1},
            "params": {
                "type": "object",
                "default": {},
                "additionalProperties": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                        {"type": "null"},
                    ]
                },
            },
        },
        "$defs": {
            "knownOp": {"type": "string", "enum": KNOWN_OPS},
            "knownTarget": {"type": "string", "enum": KNOWN_TARGETS},
        },
    }


def script_to_jsonl(text: str, *, fail_fast: bool = True) -> tuple[list[str], list[str]]:
    outputs: list[str] = []
    errors: list[str] = []
    for line_number, line in iter_script_lines(text):
        try:
            payload = parse_dsl(line).to_json_dict()
        except DSLParseError as exc:
            errors.append(f"line {line_number}: {exc}")
            if fail_fast:
                break
            continue
        outputs.append(_dump_json(payload))
    return outputs, errors


def script_to_dsl(text: str, *, fail_fast: bool = True) -> tuple[list[str], list[str]]:
    outputs: list[str] = []
    errors: list[str] = []
    for line_number, line in iter_script_lines(text):
        try:
            outputs.append(format_dsl(line))
        except DSLParseError as exc:
            errors.append(f"line {line_number}: {exc}")
            if fail_fast:
                break
    return outputs, errors


def _dump_json(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
