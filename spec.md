# ChoomLang Specification v0.5

## Goals

ChoomLang provides a deterministic command language for agent-to-agent exchange:

1. Compact human-friendly DSL (**street layer**)
2. Strict canonical JSON (**core layer**)
3. Reversible translation with stable serialization
4. Local model relay mode over Ollama (**v0.2**)
5. Structured relay, transcripts, and lenient parsing ergonomics (**v0.4**)
6. Relay reliability controls and deterministic protocol contracts (**v0.5**)

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

## CLI commands (v0.5)

- `choom translate [input]`
  - Autodetects input type when `--reverse` is not set:
    - if input starts with `{` => JSON->DSL
    - otherwise => DSL->JSON
  - Supports stdin when input is omitted or `-`
  - `--reverse` forces JSON->DSL
  - `--compact` emits minified JSON for DSL->JSON mode
- `choom teach <dsl>`: token-by-token explanation
- `choom validate [dsl]`
  - `--lenient` ignores only a trailing standalone `.`, `,`, or `;` token
  - Parse-only validation
  - success => prints `ok`, exit `0`
  - failure => prints `error: ...` to stderr, exit `2`
- `choom relay --a-model ... --b-model ...`
  - Runs A/B model relay via local Ollama HTTP API
  - `--structured` uses `/api/chat` with `stream=false` and `format` (`json` or schema object)
  - `--schema/--no-schema` controls schema-mode when structured relay is enabled
  - `--raw-json` prints raw model content alongside canonical DSL
  - `--log <path>` appends per-turn JSONL transcript records
  - `--lenient` affects DSL mode only
  - `--timeout` sets urllib timeout for all relay requests
  - `--keep-alive` forwards Ollama `keep_alive` in relay requests
  - `--no-fallback` disables automatic schema/json->DSL fallback in structured mode

- `choom fmt [dsl]`
  - `--lenient` uses the same trailing-token relaxation during parse
  - Canonicalizes a single DSL line
  - Supports stdin when input is omitted or `-`
  - Normalizes aliases (`jack` -> `gen`), sorts params lexicographically, omits `[1]`
  - Uses deterministic quoting and escapes internal `"`
- `choom script <path|->`
  - Processes multi-line ChoomLang scripts from file or stdin (`-`)
  - Ignores blank lines and `#` full-line comments
  - Supports inline comments: unquoted `#` starts a comment, quoted `#` is data
  - `--to jsonl` (default): emits one canonical JSON object per valid input line
  - `--to dsl`: emits one canonical DSL line per valid input line (same rules as `fmt`)
  - `--fail-fast` (default): stop on first parse error, exit `2`
  - `--continue`: keep processing, print per-line errors to stderr, exit `2` if any errors
- `choom schema`
  - Emits JSON Schema for canonical JSON payloads (not for DSL text grammar)
  - Includes known op/target enums and still allows custom strings for extensibility
- `choom guard`
  - Emits a reusable repair prompt
  - `--error` and `--previous` add targeted context
  - Always instructs models: `Reply with exactly one valid ChoomLang DSL line and no extra text.`

## Relay semantics (v0.5)

Relay uses Ollama endpoint `http://localhost:11434/api/chat` with fallback to `/api/generate` for DSL mode.

Required args:
- `--a-model`
- `--b-model`

Optional args:
- `--turns` (default 6)
- `--seed` (forwarded to Ollama options; ignored if endpoint/model does not use it)
- `--system-a`, `--system-b`
- `--start` (initial ChoomLang line; default `ping tool service=relay`)
- `--strict/--no-strict` (default strict)
- `--timeout` (default `180`)
- `--keep-alive` (default `300`)
- `--structured`, `--schema/--no-schema`, `--no-fallback`

Protocol contracts:
- DSL mode defaults both system prompts to a deterministic one-line DSL contract when `--system-a/--system-b` are not provided.
- Structured mode can include a minimal contract: `Return JSON only. Match the requested schema exactly.`

Structured fallback state machine:
1. If `--structured --schema`, first request uses `format=<canonical schema>` (`request_mode=structured-schema`).
2. On schema-stage timeout/HTTP error/invalid JSON response, relay warns and retries once with `format="json"` (`request_mode=structured-json`) unless `--no-fallback`.
3. If JSON stage fails:
   - strict mode: fail with clear stage diagnostics including last raw response
   - non-strict mode: fallback to guarded DSL generation (`request_mode=fallback-dsl`) and continue best-effort.

Transcript JSONL record format (`--log`):
```json
{
  "ts": "ISO8601",
  "side": "A|B",
  "model": "...",
  "mode": "dsl|structured",
  "request_mode": "dsl|structured-schema|structured-json|fallback-dsl",
  "raw": "raw assistant content",
  "parsed": {"op":"...","target":"...","count":1,"params":{}},
  "dsl": "canonical dsl or null",
  "error": "error string or null",
  "retry": 0,
  "elapsed_ms": 12,
  "timeout_s": 180,
  "keep_alive_s": 300
}
```
JSONL appends are flushed per line.

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


Structured mode behavior:
1. Relay sends canonical JSON message context to each model (not DSL text).
2. Ollama requests use `stream: false` and `format` set to either `"json"` or canonical JSON Schema object.
3. Model reply must parse as JSON object with required `op` and `target`.
4. Missing `count` defaults to `1`; missing `params` defaults to `{}`.
5. Relay converts canonical JSON to canonical DSL for display with stable sorted param keys.

Transcript JSONL record format (`--log`):
```json
{
  "ts": "ISO8601",
  "side": "A|B",
  "model": "...",
  "mode": "dsl|structured",
  "raw": "raw assistant content",
  "parsed": {"op":"...","target":"...","count":1,"params":{}},
  "dsl": "canonical dsl or null",
  "error": "error string or null",
  "retry": 0
}
```
In strict DSL mode, invalid first attempts and retry attempts are both logged with `retry` as `0` and `1` respectively.
