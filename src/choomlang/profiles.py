"""Profile loading and application helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dsl import parse_dsl, serialize_dsl


class ProfileError(ValueError):
    """Raised for profile-related failures."""


def _profiles_dir(profiles_dir: str | Path | None = None) -> Path:
    if profiles_dir is not None:
        return Path(profiles_dir)
    root = Path(__file__).resolve().parents[2]
    return root / "profiles"


def list_profiles(*, profiles_dir: str | Path | None = None) -> list[str]:
    folder = _profiles_dir(profiles_dir)
    if not folder.exists():
        return []
    return sorted(path.stem for path in folder.glob("*.json") if path.is_file())


def read_profile(name: str, *, profiles_dir: str | Path | None = None) -> dict[str, Any]:
    path = _profiles_dir(profiles_dir) / f"{name}.json"
    if not path.exists():
        raise ProfileError(f"profile not found: {name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProfileError(f"invalid profile payload for {name}: expected object")
    defaults = payload.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ProfileError(f"invalid profile payload for {name}: defaults must be object")
    return payload


def apply_profile_to_dsl(name: str, dsl_line: str, *, profiles_dir: str | Path | None = None) -> str:
    profile = read_profile(name, profiles_dir=profiles_dir)
    defaults = profile.get("defaults", {})
    parsed = parse_dsl(dsl_line)
    merged_params = dict(defaults)
    merged_params.update(parsed.params)
    return serialize_dsl(
        {
            "op": parsed.op,
            "target": parsed.target,
            "count": parsed.count,
            "params": merged_params,
        }
    )
