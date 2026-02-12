"""Canonical op/target registry and structured payload validation."""

from __future__ import annotations

from typing import Any

CANONICAL_OPS = {"gen", "classify", "summarize", "plan", "healthcheck", "toolcall", "forward"}
CANONICAL_TARGETS = {"img", "txt", "aud", "vid", "vec", "tool", "script"}
OP_ALIASES = {
    "jack": "gen",
    "scan": "classify",
    "ghost": "summarize",
    "forge": "plan",
    "ping": "healthcheck",
    "call": "toolcall",
    "relay": "forward",
}


def normalize_op(op: str) -> str:
    return OP_ALIASES.get(op, op)


def is_known_op(op: str) -> bool:
    return normalize_op(op) in CANONICAL_OPS


def is_known_target(target: str) -> bool:
    return target in CANONICAL_TARGETS


def validate_payload(
    payload: dict[str, Any],
    *,
    strict_ops: bool = True,
    strict_targets: bool = True,
) -> None:
    if not isinstance(payload.get("op"), str):
        raise ValueError(f"invalid field op={payload.get('op')!r}: expected string")
    if not isinstance(payload.get("target"), str):
        raise ValueError(f"invalid field target={payload.get('target')!r}: expected string")

    op = normalize_op(payload["op"])
    target = payload["target"]

    count = payload.get("count", 1)
    if not isinstance(count, int) or count < 1:
        raise ValueError(f"invalid field count={count!r}: expected integer >= 1")

    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"invalid field params={params!r}: expected object/dict")

    if strict_ops and op not in CANONICAL_OPS:
        raise ValueError(f"invalid field op={payload['op']!r}: unknown canonical op")

    if strict_targets and target not in CANONICAL_TARGETS:
        raise ValueError(f"invalid field target={target!r}: unknown canonical target")
