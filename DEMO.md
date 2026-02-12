# ChoomLang Structured Relay Demo

Minimal reproducible example for running a structured relay and inspecting transcript output.

## Prerequisites

- Python 3.10+
- Ollama running locally on `http://localhost:11434`
- Two local models available (examples below use `llama3.1` and `qwen2.5`)

## Step 1: Probe connectivity and model readiness

```bash
choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
```

Expected shape:

```text
probe report:
- /api/tags: ok http=200 elapsed_ms=...
- model llama3.1: ok http=200 elapsed_ms=...
- model qwen2.5: ok http=200 elapsed_ms=...
```

## Step 2: Run structured relay with warm-up and logging

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log relay.jsonl --turns 2
```

Example console output (truncated):

```text
A: gen txt tone=noir
{"count": 1, "op": "gen", "params": {"tone": "noir"}, "target": "txt"}
B: summarize txt max_tokens=120
{"count": 1, "op": "summarize", "params": {"max_tokens": 120}, "target": "txt"}
A: classify txt confidence=true labels=urgent,normal
{"count": 1, "op": "classify", "params": {"confidence": true, "labels": "urgent,normal"}, "target": "txt"}
B: plan tool dry_run=false name=scheduler
{"count": 1, "op": "plan", "params": {"dry_run": false, "name": "scheduler"}, "target": "tool"}
relay summary: turns=4 retries=0 fallbacks={"structured-json":1}
  structured-schema: avg=860.5ms median=845.0ms
  structured-json: avg=922.0ms median=922.0ms
  transcript: relay.jsonl
```

## Transcript output (`relay.jsonl`)

Each line is one JSON object with request metadata and parsed payload.

Example lines (truncated):

```json
{"dsl":"gen txt tone=noir","elapsed_ms":812,"error":null,"fallback_reason":null,"http_status":200,"keep_alive_s":300.0,"mode":"structured","model":"llama3.1","parsed":{"count":1,"op":"gen","params":{"tone":"noir"},"target":"txt"},"raw":"{\"op\":\"gen\",\"target\":\"txt\",\"count\":1,\"params\":{\"tone\":\"noir\"}}","request_id":1,"request_mode":"structured-schema","retry":0,"side":"A","stage":"structured-schema","timeout_s":240.0,"ts":"2026-01-01T12:00:00.000000+00:00"}
{"dsl":"summarize txt max_tokens=120","elapsed_ms":944,"error":null,"fallback_reason":"schema-failed:...","http_status":200,"keep_alive_s":300.0,"mode":"structured","model":"qwen2.5","parsed":{"count":1,"op":"summarize","params":{"max_tokens":120},"target":"txt"},"raw":"{\"op\":\"summarize\",\"target\":\"txt\",\"count\":1,\"params\":{\"max_tokens\":120}}","request_id":2,"request_mode":"structured-json","retry":0,"side":"B","stage":"structured-json","timeout_s":240.0,"ts":"2026-01-01T12:00:01.000000+00:00"}
```

## Summary table (human-readable)

| request_id | stage              | elapsed_ms | dsl                                        |
|------------|--------------------|-----------:|--------------------------------------------|
| 1          | structured-schema  |        812 | `gen txt tone=noir`                        |
| 2          | structured-json    |        944 | `summarize txt max_tokens=120`             |
| 3          | structured-schema  |        909 | `classify txt confidence=true labels=...`  |
| 4          | structured-schema  |        851 | `plan tool dry_run=false name=scheduler`   |

## Notes

- `stage` shows whether the response came from schema-first or JSON fallback path.
- `fallback_reason` is populated when schema stage fails and retry path is used.
- Use `--raw-json` during relay if you also want raw model replies printed to stdout.
