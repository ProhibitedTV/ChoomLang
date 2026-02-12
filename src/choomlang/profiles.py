"""Profile loading, validation, discovery, and application helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dsl import parse_dsl, serialize_dsl


class ProfileError(ValueError):
    """Raised for profile-related failures."""


_ALLOWED_TOP_KEYS = {"name", "tags", "description", "defaults", "notes"}


def _profiles_dir(profiles_dir: str | Path | None = None) -> Path:
    if profiles_dir is not None:
        return Path(profiles_dir)
    root = Path(__file__).resolve().parents[2]
    return root / "profiles"


def _profile_schema_path(profiles_dir: str | Path | None = None) -> Path:
    return _profiles_dir(profiles_dir) / "schema.json"


def _is_scalar_default(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def validate_profile_payload(payload: Any, *, source: str = "profile") -> None:
    """Validate a profile payload against the repository schema expectations."""
    if not isinstance(payload, dict):
        raise ProfileError(f"invalid profile payload for {source}: expected object")

    unknown_keys = sorted(set(payload) - _ALLOWED_TOP_KEYS)
    if unknown_keys:
        keys_text = ", ".join(unknown_keys)
        raise ProfileError(f"invalid profile payload for {source}: unexpected key(s): {keys_text}")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProfileError(f"invalid profile payload for {source}: name must be a non-empty string")

    defaults = payload.get("defaults")
    if not isinstance(defaults, dict):
        raise ProfileError(f"invalid profile payload for {source}: defaults must be object")

    for key, value in defaults.items():
        if not isinstance(key, str) or not key:
            raise ProfileError(f"invalid profile payload for {source}: defaults keys must be non-empty strings")
        if not _is_scalar_default(value):
            value_type = type(value).__name__
            raise ProfileError(
                f"invalid profile payload for {source}: defaults['{key}'] must be string|number|boolean|null, got {value_type}"
            )

    tags = payload.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or not all(isinstance(item, str) and item.strip() for item in tags):
            raise ProfileError(
                f"invalid profile payload for {source}: tags must be an array of non-empty strings"
            )

    for optional_text_key in ("description", "notes"):
        text_value = payload.get(optional_text_key)
        if text_value is not None and not isinstance(text_value, str):
            raise ProfileError(
                f"invalid profile payload for {source}: {optional_text_key} must be string"
            )


def _load_profile_from_path(path: Path) -> dict[str, Any]:
    source = path.stem
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_profile_payload(payload, source=source)
    return payload


def discover_profiles(*, profiles_dir: str | Path | None = None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    folder = _profiles_dir(profiles_dir)
    if not folder.exists():
        return {}, []

    valid: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []

    for path in sorted(folder.glob("*.json")):
        if not path.is_file() or path.name == "schema.json":
            continue
        name = path.stem
        try:
            valid[name] = _load_profile_from_path(path)
        except (ProfileError, json.JSONDecodeError, OSError) as exc:
            invalid.append(f"{name}: {exc}")

    return valid, invalid


def list_profiles(*, profiles_dir: str | Path | None = None, tag: str | None = None) -> list[str]:
    valid, _invalid = discover_profiles(profiles_dir=profiles_dir)
    names = sorted(valid)
    if tag is None:
        return names
    tag_query = tag.casefold()
    return [
        name
        for name in names
        if any(t.casefold() == tag_query for t in valid[name].get("tags", []))
    ]


def search_profiles(query: str, *, profiles_dir: str | Path | None = None) -> list[str]:
    valid, _invalid = discover_profiles(profiles_dir=profiles_dir)
    needle = query.casefold()
    matches: list[str] = []
    for name in sorted(valid):
        payload = valid[name]
        haystack_parts = [name, payload.get("description", "")]
        haystack_parts.extend(payload.get("tags", []))
        haystack = " ".join(str(part) for part in haystack_parts).casefold()
        if needle in haystack:
            matches.append(name)
    return matches


def read_profile(name: str, *, profiles_dir: str | Path | None = None) -> dict[str, Any]:
    path = _profiles_dir(profiles_dir) / f"{name}.json"
    if not path.exists():
        available = list_profiles(profiles_dir=profiles_dir)
        available_text = ", ".join(available) if available else "(none)"
        raise ProfileError(f"profile not found: {name}. available profiles: {available_text}")
    try:
        payload = _load_profile_from_path(path)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"invalid profile payload for {name}: invalid JSON ({exc})") from exc
    except OSError as exc:
        raise ProfileError(f"failed reading profile {name}: {exc}") from exc
    except ProfileError as exc:
        schema_path = _profile_schema_path(profiles_dir)
        raise ProfileError(f"{exc}. Fix {path} to match {schema_path}") from exc
    return payload


def apply_profile_to_dsl(
    name: str,
    dsl_line: str,
    *,
    profiles_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> str:
    profile = read_profile(name, profiles_dir=profiles_dir)
    defaults = profile.get("defaults", {})
    parsed = parse_dsl(dsl_line)
    merged_params = dict(defaults)
    merged_params.update(parsed.params)
    if overrides:
        merged_params.update(overrides)
    return serialize_dsl(
        {
            "op": parsed.op,
            "target": parsed.target,
            "count": parsed.count,
            "params": merged_params,
        }
    )
