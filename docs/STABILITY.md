# Stability Contract (v1.0)

This document defines ChoomLang's public stability contract starting at v1.0.

The items below are considered stable API surface unless a future MAJOR release explicitly changes them.

## 1) DSL grammar and canonical formatting

**DSL grammar stable as of v1.0.**

Stable guarantees:

- The public DSL grammar shape remains:

  ```text
  <op> <target>[count] key=value key=value ...
  ```

- Canonical alias normalization remains deterministic (aliases normalize to canonical op/target names).
- Canonical formatting remains deterministic:
  - stable token ordering rules
  - stable spacing/quoting conventions
  - stable sorted parameter keys in canonical DSL output

Compatibility expectation:

- Existing valid DSL scripts and one-line commands that rely on canonical parse/format behavior continue to parse and round-trip deterministically across v1.x.

## 2) Canonical JSON output shape

Stable guarantees:

- Canonical JSON payloads preserve the same top-level shape used by parser/serializer and CLI JSON output.
- Alias inputs normalize to canonical op/target values in JSON output.
- Deterministic output behavior is preserved (including deterministic key ordering where applicable for serialized output).

Compatibility expectation:

- Tools integrating with ChoomLang canonical JSON should not need to change for v1.x when consuming existing fields and normalized op/target semantics.

## 3) Runner artifact layout

Stable guarantees for `choom run` selected workdir layout:

- Run artifacts are written under `<workdir>/artifacts` (or `./artifacts` when `--workdir` is not set).
- Transcript records are written to `<workdir>/transcript.jsonl` (or `./transcript.jsonl` when `--workdir` is not set).
- Runner state is written to `<workdir>/state.json` (or `./state.json` when `--workdir` is not set).

Compatibility expectation:

- Automation that reads these files by location and role (artifacts vs transcript vs state) relative to the selected workdir remains compatible across v1.x.

## 4) Adapter contract for toolcall outputs

Stable guarantees:

- Adapter outputs that materialize files are saved under the run `artifacts` directory.
- Paths returned to the workflow/state/transcript for such outputs are relative artifact paths.

Compatibility expectation:

- Downstream steps and external tooling can continue to treat adapter-returned file references as relative artifact paths rooted at the run's artifacts directory.

## Out of scope

This contract does not freeze:

- internal/private Python module structure
- implementation details that do not alter the stable surfaces above
- additive, backward-compatible fields/flags introduced in MINOR releases
