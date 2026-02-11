# ChoomLang v0.1

ChoomLang is a deterministic AI-to-AI command language with two layers:

- **Street layer**: compact DSL for humans/agents
- **Core layer**: strict canonical JSON for machines

This repo implements:

- DSL parser/serializer (`DSL <-> JSON`)
- Alias normalization (street ops -> canonical ops)
- Teach mode (`token-by-token` explanation)
- CLI (`choom`)
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

Translate JSON to DSL:

```bash
choom translate --reverse '{"op":"gen","target":"img","count":2,"params":{"res":"1024x1024","style":"studio"}}'
```

Teach mode:

```bash
choom teach "jack img[2] style=studio res=1024x1024 seed=42"
```

Run tests:

```bash
pytest
```

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
