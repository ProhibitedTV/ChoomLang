"""Protocol-focused helpers added in ChoomLang v0.3."""

from __future__ import annotations

from .dsl import DSLParseError, format_dsl, parse_dsl
from .registry import CANONICAL_OPS, CANONICAL_TARGETS

KNOWN_OPS = ["gen", "classify", "summarize", "plan", "healthcheck", "toolcall", "forward"]
KNOWN_TARGETS = ["img", "txt", "aud", "vid", "vec", "tool", "script"]


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


def build_contract_prompt(mode: str = "dsl") -> str:
    """Build deterministic protocol contract text for model system prompts."""
    if mode == "dsl":
        return (
            "Reply with exactly one valid ChoomLang DSL line and no extra text. "
            "Grammar: <op> <target>[count] key=value ... "
            "Bans: no trailing punctuation, no standalone symbols, no JSON, one line only. "
            "Examples: ping txt; gen txt prompt=\"hello\"; "
            "classify txt sentiment=polarity; toolcall tool[1] name=search query=\"cats\"."
        )

    if mode == "structured":
        return "Return JSON only. Match the requested schema exactly."

    raise ValueError("mode must be 'dsl' or 'structured'")


def canonical_json_schema(*, mode: str = "strict") -> dict[str, object]:
    if mode not in {"strict", "permissive"}:
        raise ValueError("mode must be 'strict' or 'permissive'")

    if mode == "strict":
        op_schema = {"$ref": "#/$defs/knownOp"}
        target_schema = {"$ref": "#/$defs/knownTarget"}
        op_desc = "Canonical operation name."
        target_desc = "Canonical target domain."
    else:
        op_schema = {"anyOf": [{"$ref": "#/$defs/knownOp"}, {"type": "string"}]}
        target_schema = {"anyOf": [{"$ref": "#/$defs/knownTarget"}, {"type": "string"}]}
        op_desc = "Canonical operation name. Known ops are enumerated but extensions are allowed."
        target_desc = "Target domain. Known targets are enumerated but extensions are allowed."

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ChoomLang canonical payload",
        "type": "object",
        "required": ["op", "target", "count", "params"],
        "additionalProperties": False,
        "properties": {
            "op": {**op_schema, "description": op_desc},
            "target": {**target_schema, "description": target_desc},
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
        "allOf": [
            {
                "if": {
                    "properties": {
                        "op": {"const": "gen"},
                        "target": {"const": "script"},
                    },
                    "required": ["op", "target"],
                },
                "then": {
                    "properties": {
                        "params": {
                            "type": "object",
                            "required": ["text"],
                            "properties": {
                                "text": {"type": "string"},
                            },
                            "not": {"required": ["prompt"]},
                        }
                    }
                },
            }
        ],
        "$defs": {
            "knownOp": {"type": "string", "enum": KNOWN_OPS},
            "knownTarget": {"type": "string", "enum": KNOWN_TARGETS},
        },
    }


def parse_script_text(text: str) -> list[dict[str, object]]:
    """Parse a multi-line ChoomLang script string into canonical payload rows."""
    parsed_rows: list[dict[str, object]] = []
    for line_number, line in iter_script_lines(text):
        try:
            parsed_rows.append(parse_dsl(line).to_json_dict())
        except DSLParseError as exc:
            raise DSLParseError(f"line {line_number}: {exc}") from exc
    return parsed_rows


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
