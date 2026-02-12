# ChoomLang

Deterministic command protocol for agent-to-agent exchanges, with a compact DSL, canonical JSON, and an Ollama relay runtime.

**v0.9 highlights:** generic profiles, profile schema validation, profile search/filter/override UX, and full version roll updates.

## What Problem ChoomLang Solves

LLM output drift is common: the same prompt often produces different wrappers, key ordering, or extra text. That makes automation fragile.

ChoomLang addresses this by combining three parts:

- **Canonical JSON** for deterministic machine handling.
- **Compact DSL** for short human/agent-authored commands.
- **Relay runtime** for model-to-model turn exchange with validation, fallback, and transcript logging.

Why this split:

- JSON alone is explicit but verbose for fast iteration.
- DSL alone is compact but easier for models to break.
- ChoomLang keeps both and normalizes to a canonical structure.

## 60-Second Quick Start

### Bash (macOS/Linux)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl
```

If `--probe` fails, verify Ollama is running and both model names are available.


## Updated Quick Start

```bash
pip install -e .
choom profile list
choom profile apply wallpaper "gen img prompt="night skyline"" --set style=retro
choom lint "jack txt tone=noir"
choom run "toolcall tool name=echo trace=demo" --dry-run
```

```powershell
pip install -e .
choom profile list
choom profile apply wallpaper "gen img prompt="night skyline"" --set style=retro
choom lint "jack txt tone=noir"
choom run "toolcall tool name=echo trace=demo" --dry-run
```

## Profiles

Profiles are reusable JSON defaults stored under `profiles/` and validated against `profiles/schema.json` when loaded.

- `choom profile list`
- `choom profile list --tag <tag>`
- `choom profile search <substring>`
- `choom profile show <name>`
- `choom profile apply <name> "<dsl>" --set key=value --set key=value`

Apply rules:

- only `params` keys are affected
- `op`, `target`, and `count` are never changed
- merge order: parse DSL -> apply profile defaults for missing keys -> apply `--set` overrides
- `op`, `target`, and `count` are preserved
- final DSL output is canonical with sorted params

Bash examples:

```bash
choom profile list --tag image
choom profile search portrait
choom profile apply wallpaper "gen img prompt=\"night skyline\"" --set style=retro --set seed=7
```

PowerShell examples:

```powershell
choom profile list --tag image
choom profile search portrait
choom profile apply wallpaper "gen img prompt="night skyline"" --set style=retro --set seed=7
```

## Run toolcall (safe adapters)

`choom run` executes only canonical `toolcall tool` commands.

Built-ins in v0.8:

- `name=echo`: prints params
- `name=write_file`: writes `text` to `path` under `./out` (or `--out-dir`)

Examples:

```bash
choom run "toolcall tool name=echo id=123 role=worker"
choom run "toolcall tool name=write_file path=notes/todo.txt text=hello"
choom run "toolcall tool name=write_file path=notes/todo.txt text=hello" --dry-run
```

Path traversal is blocked for `write_file`. Network/shell adapters are intentionally not included in v0.8.

## Lint (warnings-only)

`choom lint` is non-blocking by design and does not reject unknown params.

- warns on non-canonical DSL (suggests `choom fmt`)
- warns on suspicious standalone punctuation tokens (unless `--lenient`)
- warns on unknown op/target only with `--strict-ops` / `--strict-targets`
- warns on non-conventional param keys

Exit codes:

- `0`: clean
- `1`: warnings
- `2`: parse/runtime errors

## DSL Overview

Grammar:

```text
<op> <target>[count] key=value key=value ...
```

Examples:

```text
gen img[2] style=studio res=1024x1024
scan txt labels=urgent,normal confidence=true
ping tool service=renderer timeout=1.5
```

Alias normalization is centralized in `src/choomlang/registry.py` and applied during parse/serialization. Example mappings:

- `jack -> gen`
- `scan -> classify`
- `ghost -> summarize`
- `forge -> plan`
- `ping -> healthcheck`
- `call -> toolcall`
- `relay -> forward`

## Structured Relay Mode

Use structured mode when you want deterministic model output under relay:

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --schema
```

Behavior:

1. With `--structured`, relay requests JSON output from Ollama.
2. With schema enabled (`--schema`, default), relay uses schema mode:
   - strict schema when `--strict` (default)
   - permissive schema otherwise
3. If schema response fails validation/parse/transport, relay retries once with `format="json"`.
4. If that also fails:
   - `--strict` (default) returns an error.
   - Without strict, relay may fall back to DSL unless `--no-fallback` is set.

Use `--no-schema` if a model/version struggles with schema-format responses but can still return valid JSON with `format="json"`.

If structured validation rejects unknown values, use:
- `--allow-unknown-op`
- `--allow-unknown-target`

## Example Transcript (JSONL Snippet)

When `--log relay.jsonl` is enabled, each turn appends one record.

```json
{"dsl":"gen txt tone=noir","elapsed_ms":812,"error":null,"fallback_reason":null,"http_status":200,"keep_alive_s":300.0,"mode":"structured","model":"llama3.1","parsed":{"count":1,"op":"gen","params":{"tone":"noir"},"target":"txt"},"raw":"{\"op\":\"gen\",\"target\":\"txt\",\"count\":1,\"params\":{\"tone\":\"noir\"}}","request_id":1,"request_mode":"structured-schema","retry":0,"side":"A","stage":"structured-schema","timeout_s":240.0,"ts":"2026-01-01T12:00:00.000000+00:00"}
{"dsl":"summarize txt max_tokens=120","elapsed_ms":944,"error":null,"fallback_reason":"schema-failed:...","http_status":200,"keep_alive_s":300.0,"mode":"structured","model":"qwen2.5","parsed":{"count":1,"op":"summarize","params":{"max_tokens":120},"target":"txt"},"raw":"{\"op\":\"summarize\",\"target\":\"txt\",\"count\":1,\"params\":{\"max_tokens\":120}}","request_id":2,"request_mode":"structured-json","retry":0,"side":"B","stage":"structured-json","timeout_s":240.0,"ts":"2026-01-01T12:00:01.000000+00:00"}
```

See [DEMO.md](DEMO.md) for a complete minimal run.


## Shell Completion

Generate completion scripts directly from the CLI:

```bash
choom completion bash
choom completion zsh
```

```powershell
choom completion powershell
```

If you omit the shell argument, Choom tries to auto-detect your environment and prints a suitable script.

## Relay Demo Shortcut

Run a predefined structured relay demo:

```bash
choom demo
```

This runs `llama3.2:latest` ↔ `qwen2.5:latest` for 4 turns, starts from:

`gen txt prompt="ChoomLang in action: describe a client-server protocol in 5 lines"`

and saves transcript records to `choom_demo.jsonl`.

## CLI Reference (Condensed)

Use `choom --help` and `choom <command> --help` for full arguments.

- `translate`: DSL ↔ JSON conversion (`--reverse`, `--compact`)
- `fmt`: canonicalize one DSL line
- `validate`: parse-check DSL line
- `script`: process multi-line scripts (`--to jsonl|dsl`, `--continue`)
- `schema`: print canonical JSON schema (`--mode strict|permissive`)
- `guard`: print model repair prompt
- `relay`: Ollama relay (`--structured`, `--schema/--no-schema`, `--allow-unknown-op`, `--allow-unknown-target`, `--probe`, `--warm`, `--log`)
- `demo`: predefined structured relay example run
- `completion`: print shell completion script
- `teach`: token-by-token DSL explanation

## Recommended Workflows

### Relay: Probe → Warm → Structured

```bash
choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl
```

### Script + Validate Chain

```bash
choom validate "gen img style=studio"
choom script examples/dsl.txt --to jsonl
```

## References

- Protocol and grammar details: [spec.md](spec.md)
- Grammar notes: [grammar.md](grammar.md)
- Relay walkthrough: [DEMO.md](DEMO.md)

## Contributing

- Python 3.10+
- Install editable package: `pip install -e .`
- Run tests: `pytest`
- Keep changes deterministic and focused
- For CLI behavior updates, keep docs and examples in sync

## Release Steps

See [RELEASE.md](RELEASE.md) for test/build/tag/release guidance.
