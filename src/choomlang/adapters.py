"""Built-in tool adapters and registry helpers."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .errors import RunError

Adapter = Callable[[dict[str, Any], Path, bool], str]


def _validate_relative_artifact_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if not raw_path:
        raise RunError("adapter path must not be empty")
    if path.is_absolute():
        raise RunError(f"unsafe artifact path (absolute paths are not allowed): {raw_path}")
    if ".." in path.parts:
        raise RunError(f"unsafe artifact path (path traversal is not allowed): {raw_path}")
    return path


def resolve_artifact_path(base_dir: Path, raw_path: str) -> tuple[Path, str]:
    rel_path = _validate_relative_artifact_path(raw_path)
    resolved = (base_dir / rel_path).resolve()
    base_resolved = base_dir.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise RunError(f"unsafe artifact path (must stay within artifacts): {raw_path}")
    return resolved, rel_path.as_posix()


def _adapter_echo(params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    _ = artifacts_dir
    _ = dry_run
    return json.dumps(params, sort_keys=True)


def _adapter_write_file(params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("write_file requires param 'path'")
    text = str(params.get("text", ""))
    destination, relative = resolve_artifact_path(artifacts_dir, raw_path)
    if dry_run:
        return relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return relative


def _adapter_read_file(params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    _ = dry_run
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("read_file requires param 'path'")
    destination, _ = resolve_artifact_path(artifacts_dir, raw_path)
    if not destination.exists() or not destination.is_file():
        raise RunError(f"read_file path does not exist or is not a file: {raw_path}")
    return destination.read_text(encoding="utf-8")


def _adapter_mkdir(params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    raw_path = str(params.get("path", ""))
    if not raw_path:
        raise RunError("mkdir requires param 'path'")
    destination, relative = resolve_artifact_path(artifacts_dir, raw_path)
    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)
    return relative


def _adapter_list_dir(params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    _ = dry_run
    raw_path = str(params.get("path", "."))
    destination, _ = resolve_artifact_path(artifacts_dir, raw_path)
    if not destination.exists() or not destination.is_dir():
        raise RunError(f"list_dir path does not exist or is not a directory: {raw_path}")
    entries = sorted(item.name for item in destination.iterdir())
    return json.dumps(entries, separators=(",", ":"))


BUILTIN_ADAPTERS: dict[str, Adapter] = {
    "echo": _adapter_echo,
    "list_dir": _adapter_list_dir,
    "mkdir": _adapter_mkdir,
    "read_file": _adapter_read_file,
    "write_file": _adapter_write_file,
}


def run_adapter(name: str, params: dict[str, Any], artifacts_dir: Path, dry_run: bool) -> str:
    adapter = BUILTIN_ADAPTERS.get(name)
    if adapter is None:
        known = ", ".join(sorted(BUILTIN_ADAPTERS))
        raise RunError(f"unknown tool adapter '{name}'. known adapters: {known}")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return adapter(params, artifacts_dir, dry_run)
