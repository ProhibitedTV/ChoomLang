# Versioning Policy

ChoomLang follows [Semantic Versioning](https://semver.org/) starting with v1.0.

Version format:

```text
MAJOR.MINOR.PATCH
```

Pre-release builds may use PEP 440-compatible suffixes (for example, `1.0.0rc1`) and can be labeled in release notes as `v1.0.0-rc.1`.

## MAJOR

Increment MAJOR for backward-incompatible changes to stable public surfaces, including the v1.0 stability contract in `docs/STABILITY.md`:

- DSL grammar or canonical formatting behavior changes that break existing deterministic round-trips.
- Canonical JSON shape or normalized semantics changes that break existing consumers.
- Runner artifact layout contract changes (`<workdir>/artifacts`, `<workdir>/transcript.jsonl`, `<workdir>/state.json`).
- Adapter output contract changes (file outputs no longer stored under artifacts and/or no longer returned as relative artifact paths).

## MINOR

Increment MINOR for backward-compatible feature additions, such as:

- new commands, flags, adapters, or schema fields that do not break existing usage
- additive documentation/spec updates
- optional behavior that preserves previous defaults and compatibility

## PATCH

Increment PATCH for backward-compatible fixes and maintenance, such as:

- bug fixes preserving public contracts
- determinism/reliability improvements without changing stable API behavior
- documentation clarifications with no behavior change

## Pre-1.0 note

Before v1.0, project releases may evolve quickly. The explicit stability contract applies from v1.0 onward.
