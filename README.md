# ChoomLang v0.4

ChoomLang is a deterministic AI-to-AI command language with two layers:

- **Street layer**: compact DSL for humans/agents
- **Core layer**: strict canonical JSON for machines

This repo implements:

- DSL parser/serializer (`DSL <-> JSON`)
- Alias normalization (street ops -> canonical ops)
- Teach mode (`token-by-token` explanation)
- Validate mode (parse-only lint for DSL lines)
- Ollama-backed relay mode (`choom relay`)
- CLI (`choom`)
- v0.4 structured relay + logging + lenient parsing ergonomics
- Tests + CI

## Install

```bash
pip install -e .
```

## Quickstart

Translate DSL to canonical JSON:

```bash
choom translate "jack img[2] style=studio res=1024x1024"
```

Translate JSON to DSL (`--reverse`):

```bash
choom translate --reverse '{"op":"gen","target":"img","count":2,"params":{"res":"1024x1024","style":"studio"}}'
```

Translate with autodetect (JSON input auto-converts to DSL):

```bash
choom translate '{"op":"gen","target":"img","count":2,"params":{"res":"1024x1024","style":"studio"}}'
```

Compact JSON output:

```bash
choom translate "gen txt tone=noir" --compact
```

Validate DSL input (parse-only):

```bash
choom validate "gen img[2] style=studio"
```

Teach mode:

```bash
choom teach "jack img[2] style=studio res=1024x1024 seed=42"
```

Relay mode (two local Ollama models speaking ChoomLang):

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --turns 4
```

Relay with custom system prompts and starter message:

```bash
choom relay \
  --a-model llama3.1 \
  --b-model qwen2.5 \
  --system-a "You are concise and practical." \
  --system-b "You are cautious and verify assumptions." \
  --start "scan txt labels=urgent,normal confidence=true" \
  --turns 3
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

Lenient mode note: `validate`, `fmt`, and `relay` support `--lenient` to ignore only a final standalone `.`, `,`, or `;` token.

## DSL shape

```text
<op> <target>[count] key=value key=value ...
```

- `op`: required operation string (aliases accepted)
- `target`: required (`img|txt|aud|vid|vec|tool` by default; extensible)
- `count`: optional integer, defaults to `1`
- key/value params: optional and space-delimited
- values: bareword, quoted string, int, float, bool

## Examples

1. `jack img[3] style=cyberpunk neon=++ res=1920x1080 seed=42`
2. `gen img style=studio res=1024x1024`
3. `scan img[2] model="vision v2" threshold=0.82`
4. `classify txt labels="urgent,normal" confidence=true`
5. `ghost txt length=short tone=noir`
6. `summarize txt[4] max_tokens=120`
7. `forge vec[5] objective="route planning" budget=3.5`
8. `plan tool name=scheduler dry_run=false`
9. `ping tool service=renderer timeout=1.5`
10. `healthcheck tool region=nightcity`
11. `call tool name="weather.api" city="New Tokyo"`
12. `relay txt channel=ops priority=2`

Canonical op normalization examples:

- `jack` -> `gen`
- `scan` -> `classify`
- `ghost` -> `summarize`
- `forge` -> `plan`
- `ping` -> `healthcheck`
- `call` -> `toolcall`
- `relay` -> `forward`

See [`spec.md`](spec.md) and [`grammar.md`](grammar.md) for full details.
