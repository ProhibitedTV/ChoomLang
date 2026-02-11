"""Core DSL parsing and serialization for ChoomLang."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ALIAS_TO_CANON = {
    "jack": "gen",
    "scan": "classify",
    "ghost": "summarize",
    "forge": "plan",
    "ping": "healthcheck",
    "call": "toolcall",
    "relay": "forward",
}

HEADER_RE = re.compile(r"^(?P<target>[A-Za-z_][A-Za-z0-9_-]*)(?:\[(?P<count>[^\]]+)\])?$")


class DSLParseError(ValueError):
    """Raised when a DSL line cannot be parsed."""


@dataclass(frozen=True)
class ParsedCommand:
    op: str
    target: str
    count: int
    params: dict[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "target": self.target,
            "count": self.count,
            "params": dict(self.params),
        }


def canonicalize_op(op: str) -> str:
    return ALIAS_TO_CANON.get(op, op)


def parse_dsl(line: str, *, lenient: bool = False) -> ParsedCommand:
    tokens = _tokenize(line)
    if lenient:
        tokens = _strip_trailing_punctuation_token(tokens)
    if len(tokens) < 2:
        raise DSLParseError("invalid header: expected '<op> <target>[count] ...'")

    op = tokens[0]
    target, count = _parse_target_count(tokens[1])

    params: dict[str, Any] = {}
    for token in tokens[2:]:
        if "=" not in token:
            raise DSLParseError(f"malformed kv: missing '=' in token '{token}'")
        key, raw_value = token.split("=", 1)
        if not key:
            raise DSLParseError(f"malformed kv: empty key in token '{token}'")
        if raw_value == "":
            raise DSLParseError(f"malformed kv: empty value for key '{key}'")
        params[key] = _coerce_value(raw_value)

    return ParsedCommand(op=canonicalize_op(op), target=target, count=count, params=params)


def serialize_dsl(command: dict[str, Any] | ParsedCommand) -> str:
    if isinstance(command, ParsedCommand):
        payload = command.to_json_dict()
    else:
        payload = command

    op = canonicalize_op(str(payload["op"]))
    target = str(payload["target"])
    count = int(payload.get("count", 1))
    if count < 1:
        raise DSLParseError(f"bad count: expected >= 1, got {count}")

    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise DSLParseError("malformed params: expected object/dict")

    parts = [op, target if count == 1 else f"{target}[{count}]"]
    for key in sorted(params):
        parts.append(f"{key}={_serialize_value(params[key])}")
    return " ".join(parts)


def format_dsl(line: str, *, lenient: bool = False) -> str:
    """Return canonical single-line DSL formatting for input."""
    return serialize_dsl(parse_dsl(line, lenient=lenient))


def _strip_trailing_punctuation_token(tokens: list[str]) -> list[str]:
    if tokens and tokens[-1] in {".", ",", ";"}:
        return tokens[:-1]
    return tokens


def _parse_target_count(token: str) -> tuple[str, int]:
    match = HEADER_RE.match(token)
    if not match:
        raise DSLParseError(f"invalid header: invalid target/count segment '{token}'")

    target = match.group("target")
    raw_count = match.group("count")
    if raw_count is None:
        return target, 1

    if not re.fullmatch(r"[0-9]+", raw_count):
        raise DSLParseError(f"bad count: expected positive integer, got '{raw_count}'")
    count = int(raw_count)
    if count < 1:
        raise DSLParseError(f"bad count: expected >= 1, got {count}")
    return target, count


def _tokenize(line: str) -> list[str]:
    line = line.strip()
    if not line:
        raise DSLParseError("invalid header: empty input")

    tokens: list[str] = []
    current: list[str] = []
    in_quote = False
    escape = False

    for ch in line:
        if in_quote:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_quote = False
            continue

        if ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
            continue

        current.append(ch)
        if ch == '"':
            in_quote = True

    if in_quote:
        raise DSLParseError("unterminated quote: missing closing '\"'")

    if current:
        tokens.append("".join(current))

    return tokens


def _coerce_value(raw: str) -> Any:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        return _unescape_quoted(inner)

    lower = raw.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False

    if re.fullmatch(r"-?[0-9]+", raw):
        return int(raw)

    if re.fullmatch(r"-?[0-9]+\.[0-9]+", raw):
        return float(raw)

    return raw


def _unescape_quoted(text: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in {'"', "\\"}:
                result.append(nxt)
                i += 2
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def _serialize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)

    text = str(value)
    if _needs_quotes(text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _needs_quotes(text: str) -> bool:
    if text == "":
        return True
    for ch in text:
        if ch.isspace() or ch in {'"', '='}:
            return True
    return False
