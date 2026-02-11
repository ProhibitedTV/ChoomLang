# ChoomLang Specification v0.2

## Goals

ChoomLang provides a deterministic command language for agent-to-agent exchange:

1. Compact human-friendly DSL (**street layer**)
2. Strict canonical JSON (**core layer**)
3. Reversible translation with stable serialization
4. Local model relay mode over Ollama (**v0.2**)

## Canonical JSON form

```json
{
  "op": "...",
  "target": "...",
  "count": 1,
  "params": {}
}
```

Rules:
- `op` is canonicalized (aliases normalized)
- `target` is required
- `count` is integer >= 1, defaults to 1
- `params` is object (possibly empty)
- JSON->DSL sorts parameter keys lexicographically
- CLI JSON output uses deterministic ordering (`sort_keys=True`)

## DSL form

```text
<op> <target>[count] key=value key=value ...
```

Required:
- `op`
- `target` with optional `[count]`

Optional:
- key=value pairs

Value types:
- bool: `true`/`false`
- int: `42`, `-7`
- float: `0.82`, `-1.5`
- quoted string: `"New Tokyo"` (supports escaped quotes `\"`)
- bareword: `cyberpunk`, `1920x1080`, `++`

## Alias table

| Alias | Canonical op |
|---|---|
| jack | gen |
| scan | classify |
| ghost | summarize |
| forge | plan |
| ping | healthcheck |
| call | toolcall |
| relay | forward |

Both aliases and canonical operations are accepted in DSL input.
Canonical JSON always stores canonical operation names.

## CLI commands (v0.2)

- `choom translate [input]`
  - Autodetects input type when `--reverse` is not set:
    - if input starts with `{` => JSON->DSL
    - otherwise => DSL->JSON
  - Supports stdin when input is omitted or `-`
  - `--reverse` forces JSON->DSL
  - `--compact` emits minified JSON for DSL->JSON mode
- `choom teach <dsl>`: token-by-token explanation
- `choom validate [dsl]`
  - Parse-only validation
  - success => prints `ok`, exit `0`
  - failure => prints `error: ...` to stderr, exit `2`
- `choom relay --a-model ... --b-model ...`
  - Runs A/B model relay via local Ollama HTTP API

## Relay semantics (v0.2)

Relay uses Ollama endpoint `http://localhost:11434/api/chat` with fallback to `/api/generate`.

Required args:
- `--a-model`
- `--b-model`

Optional args:
- `--turns` (default 6)
- `--seed` (forwarded to Ollama options; ignored if endpoint/model does not use it)
- `--system-a`, `--system-b`
- `--start` (initial ChoomLang line; default `ping tool service=relay`)
- `--strict/--no-strict` (default strict)

Strict mode behavior:
1. Model output must be valid ChoomLang DSL.
2. If invalid, CLI sends a corrective instruction to that same model and retries once.
3. If second attempt is invalid, relay aborts with a clear error.

Safety limits:
- Relay enforces message size limits.
- Relay stops after configured turn count.
- Connection and HTTP failures produce user-facing relay errors.

## Default targets (extensible)

`img`, `txt`, `aud`, `vid`, `vec`, `tool`

Targets outside this set are allowed by parser for extensibility.

## Error rules

Parser emits specific error categories:
- **invalid header**: missing/invalid `op target[count]`
- **bad count**: malformed, zero, negative, or non-integer count
- **malformed kv**: token missing `=` or invalid key/value formatting
- **unterminated quote**: missing closing `"` in quoted string

Errors include token or segment context when possible.

## Determinism and reversibility

- Lexer preserves token boundaries with quote awareness.
- Type coercion is deterministic by precedence:
  1. quoted string
  2. bool (`true`/`false`)
  3. int
  4. float
  5. bareword string
- Serialization quotes only when required.
- `params` key ordering is sorted for stable output.

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
