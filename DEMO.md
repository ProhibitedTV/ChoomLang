# Relay Demo (Minimal Reproducible)

This is the shortest practical flow to verify the Ollama-backed relay in a deterministic, repeatable way.

## 1) Environment setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

## 2) Install

```bash
pip install -e .
```

## 3) Probe (connectivity + model readiness)

```bash
choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
```

## 4) Structured warm run with logging

```bash
choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log transcript.jsonl
```

## Screenshot-ready terminal output example

```text
$ choom relay --probe --a-model llama3.1 --b-model qwen2.5 --timeout 240 --keep-alive 300
probe report:
- /api/tags: ok http=200 elapsed_ms=21
- model llama3.1: ok http=200 elapsed_ms=389
- model qwen2.5: ok http=200 elapsed_ms=403

$ choom relay --a-model llama3.1 --b-model qwen2.5 --structured --warm --timeout 240 --keep-alive 300 --log transcript.jsonl
relay summary: turns=12 retries=1 fallbacks={"structured-json": 1}
  structured-json: avg=512.67ms median=497.0ms
  structured-schema: avg=476.42ms median=462.0ms
  transcript: transcript.jsonl
A: gen txt tone=noir
{"count": 1, "op": "gen", "params": {"tone": "noir"}, "target": "txt"}
B: classify txt label=concise
{"count": 1, "op": "classify", "params": {"label": "concise"}, "target": "txt"}
```

## Transcript record key walkthrough

Each line in `transcript.jsonl` is a JSON object created by `build_transcript_record`. Below are the key fields commonly used when reading relay traces:

- `ts`: UTC ISO-8601 timestamp for when the record was written.
- `request_id`: monotonically increasing integer ID for each model call in a relay run.
- `side`: speaker label (`"A"` or `"B"`).
- `model`: model name used for that step.
- `mode`: high-level relay mode (`"structured"` or `"dsl"`).
- `stage`: request stage (`"dsl"`, `"structured-schema"`, `"structured-json"`, or `"fallback-dsl"`).
- `http_status`: HTTP status code from Ollama when available.
- `parsed`: normalized canonical JSON payload parsed from the model reply (or `null` on failure records).
- `dsl`: deterministic DSL string rendered from `parsed` (or the DSL-mode reply).
- `retry`: integer retry counter for that step (`0` for first attempt, `1` after schema->json retry, etc.).
- `elapsed_ms`: integer request latency in milliseconds.
- `fallback_reason`: `null` when no fallback occurred, otherwise a reason string (for example `"schema-failed:..."`).

## Truncated `transcript.jsonl` sample

```jsonl
{"ts":"2026-02-12T10:15:30.102345+00:00","request_id":1,"side":"A","model":"llama3.1","mode":"structured","stage":"structured-schema","http_status":200,"parsed":{"op":"gen","target":"txt","count":1,"params":{"tone":"noir"}},"dsl":"gen txt tone=noir","retry":0,"elapsed_ms":462,"fallback_reason":null}
{"ts":"2026-02-12T10:15:31.021204+00:00","request_id":2,"side":"B","model":"qwen2.5","mode":"structured","stage":"structured-json","http_status":200,"parsed":{"op":"classify","target":"txt","count":1,"params":{"label":"concise"}},"dsl":"classify txt label=concise","retry":1,"elapsed_ms":497,"fallback_reason":"schema-failed:Ollama request timed out after 240s"}
```
