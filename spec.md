# ChoomLang Specification v0.1

## Goals

ChoomLang provides a deterministic command language for agent-to-agent exchange:

1. Compact human-friendly DSL (**street layer**)
2. Strict canonical JSON (**core layer**)
3. Reversible translation with stable serialization

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

## Alias table (v0.1)

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
