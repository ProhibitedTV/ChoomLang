# Changelog

## 0.10.1

- Added `script` as a canonical target for payload validation and schema generation.
- Added multi-line script validation helper (`parse_script_text`) and CLI entrypoints: `choom validate-script` and `choom script --validate-only`.
- Updated structured relay validation for `gen script`: requires `params.text`, rejects `params.prompt`, and validates parseable script content.
- Extended runner support for `gen script id=...`: stores script text in state and writes `artifacts/<id>.choom` when `id` is provided.
- Added tests for script parsing, structured relay script validation, and runner script persistence.

## 0.10.0

- Added the `choom run` workflow runner for multi-step `.choom` execution with deterministic step records.
- Added workflow persistence via `--workdir`, including `state.json` storage, `transcript.jsonl` append-only logging, and resume semantics through `--resume` (auto or explicit step index).
- Expanded safe adapter coverage with fail-closed artifact path validation for local filesystem operations.
- Added Ollama runner adapter support (`name=ollama` / `name=ollama_chat`) with fake-client tested execution paths.
- Hardened deterministic logging and state semantics: sorted-key JSON writes, atomic state updates, and stable completed-step counting for resume behavior.

## 0.9.0

- Replaced project-specific profiles with a generic profile pack spanning text, image, general, and tool workflows.
- Added `profiles/schema.json` and runtime profile validation with actionable errors.
- Added profile UX improvements: `choom profile list --tag`, `choom profile search`, and `choom profile apply --set` overrides.
- Improved profile docs in README and added `CONTRIBUTING.md` guidance for adding new profiles.
- Rolled package version metadata and tests to 0.9.0.

## 0.8.0

- Added profile support with `choom profile list|show|apply` and repository-shipped examples under `profiles/`.
- Added optional warning-focused lint command: `choom lint`.
- Added safe local execution skeleton: `choom run` for canonical `toolcall tool` commands.
- Added built-in run adapters: `echo` and safe `write_file` restricted to an output directory.
- Added deterministic profile apply behavior that only fills missing `params` keys.
- Added parameter convention documentation and release guidance.

## 0.7.0

- Added canonical op/target registry and alias normalization.
- Added strict/permissive schema modes and improved unknown op/target diagnostics.
- Expanded relay structured validation and transcript reporting.

## 0.6.0

- Added relay runtime with local Ollama integration.
- Added demo command and completion command support.

## 0.5.0

- Added schema and guard helper commands.
- Added script processing for multi-line `.choom` content.

## 0.4.0

- Added deterministic formatter and validation improvements.

## 0.3.0

- Added protocol helpers and canonical schema generation.

## 0.2.0

- Added DSL teaching and translation helpers.

## 0.1.0

- Initial parser/serializer and CLI foundation.
