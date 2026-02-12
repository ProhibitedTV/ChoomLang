# ChoomLang

ChoomLang is a deterministic two-layer agent protocol that maps a compact DSL to canonical JSON for reliable machine execution.

## What Problem ChoomLang Solves

- **LLM formatting drift:** free-form model output is inconsistent across turns and providers.
- **Need deterministic agent protocol:** agents need strict, parseable messages instead of prompt-shaped text.
- **JSON verbosity:** raw JSON is precise but expensive for humans (and many agent prompts) to write repeatedly.
- **DSL fragility:** lightweight command syntaxes often break without a canonical machine representation.
- **ChoomLang solution:** a canonical JSON contract + compact DSL + relay runtime for stable agent-to-agent exchange.

## 60-Second Quick Start

Create and activate a virtual environment.

Unix/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install:

```bash
pip install -e .
```

Probe connectivity and model readiness:

```bash
choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
```

Run structured relay with warmup and logging:

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl
```

## Stdin / piping examples

Read translation input from stdin:

```bash
echo 'gen txt tone=noir' | choom translate
```

Read JSON from stdin and auto-detect reverse translation:

```bash
echo '{"op":"gen","target":"txt","count":1,"params":{"tone":"noir"}}' | choom translate
```

Validate stdin:

```bash
echo 'jack img[2] style=studio' | choom validate
```

Run tests:

```bash
pytest
```

Format one DSL line to canonical form:

```bash
choom fmt 'jack txt[1] z=2 a="two words"'
# gen txt a="two words" z=2
```

Process script files (JSONL by default):

```bash
choom script examples/dsl.txt
```

Process stdin script and keep going on parse errors:

```bash
cat batch.choom | choom script - --to dsl --continue
```

Emit JSON Schema for canonical JSON payloads:

```bash
choom schema
```

Print a reusable guard/repair prompt:

```bash
choom guard
choom guard --error "invalid header" --previous "hello world"
```

Structured relay mode (canonical JSON over Ollama format):

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --schema
```

Relay transcript logging (JSONL):

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --log relay.jsonl
```


Recommended on Windows PowerShell:

```powershell
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --schema --timeout 240 --keep-alive 600
```

Relay reliability controls:
- `--timeout SECONDS` (default `180`) applies to all Ollama HTTP requests.
- `--keep-alive SECONDS` (default `300`) is sent as Ollama `keep_alive` for `/api/chat` and `/api/generate`.
- `--no-fallback` disables structured auto-fallback.

Structured fallback behavior:
1. `--structured --schema` tries schema format first (unless `--no-schema`).
2. On timeout/HTTP/non-JSON or invalid structured payload, relay logs a fallback reason and retries once with `format="json"`.
3. If JSON retry fails: `--strict` exits with stage + reason + raw response; otherwise relay may fall back to DSL unless `--no-fallback` is set.

`choom relay --probe` quick check (connectivity + model readiness):

```bash
choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
```

Recommended Windows flow:
1. `choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300`
2. `choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300`

Copy/paste structured demo:

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl
```


Lenient mode note: `validate`, `fmt`, and `relay` support `--lenient` to ignore only a final standalone `.`, `,`, or `;` token.

## DSL shape

```text
<op> <target>[count] key=value key=value ...
```

- `op` + `target`: required operation and modality/tool target; aliases are accepted and normalized to canonical ops in JSON.
- `[count]` + `key=value ...`: optional repeat count (default `1`) and optional space-delimited params with bare or quoted values.

## Examples

1. Generation: `gen img style=studio res=1024x1024`
2. Classification alias: `scan img[2] model="vision v2" threshold=0.82` (`scan` normalizes to `classify`)
3. Tool-forward case: `relay txt channel=ops priority=2` (`relay` normalizes to `forward`)

See [`spec.md`](spec.md) and [`grammar.md`](grammar.md) for full details.
