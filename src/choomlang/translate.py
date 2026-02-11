"""High-level translation helpers."""

from __future__ import annotations

import json
from typing import Any

from .dsl import parse_dsl, serialize_dsl


def dsl_to_json(dsl_line: str) -> dict[str, Any]:
    return parse_dsl(dsl_line).to_json_dict()


def dsl_to_json_text(dsl_line: str, *, indent: int = 2) -> str:
    return json.dumps(dsl_to_json(dsl_line), indent=indent, sort_keys=True)


def json_to_dsl(payload: dict[str, Any]) -> str:
    return serialize_dsl(payload)


def json_text_to_dsl(json_text: str) -> str:
    payload = json.loads(json_text)
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return json_to_dsl(payload)
