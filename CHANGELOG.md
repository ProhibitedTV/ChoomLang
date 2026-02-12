# Changelog

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
