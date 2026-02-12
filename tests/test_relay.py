import json

import pytest

from choomlang.protocol import build_contract_prompt
from choomlang.relay import (
    RelayError,
    build_transcript_record,
    decide_structured_recovery,
    parse_structured_reply,
    strict_validate_with_retry,
)


def test_strict_validate_with_retry_accepts_valid_line():
    line, payload = strict_validate_with_retry("gen img style=studio", strict=True)
    assert line == "gen img style=studio"
    assert payload["op"] == "gen"


def test_strict_validate_with_retry_repairs_once():
    retried = []

    def retry(prompt: str) -> str:
        retried.append(prompt)
        return "scan txt confidence=true"

    line, payload = strict_validate_with_retry("oops", strict=True, retry=retry)
    assert retried
    assert "Grammar:" in retried[0]
    assert line == "scan txt confidence=true"
    assert payload["op"] == "classify"


def test_strict_validate_with_retry_fails_after_bad_retry():
    def retry(_: str) -> str:
        return "still not dsl"

    with pytest.raises(RelayError, match="after retry"):
        strict_validate_with_retry("nope", strict=True, retry=retry)


def test_parse_structured_reply_defaults_and_dsl():
    payload, dsl = parse_structured_reply('{"op":"gen","target":"txt"}')
    assert payload == {"op": "gen", "target": "txt", "count": 1, "params": {}}
    assert dsl == "gen txt"


def test_parse_structured_reply_rejects_invalid_json():
    with pytest.raises(RelayError, match="valid JSON"):
        parse_structured_reply("nope")


def test_contract_builder_dsl_has_grammar_bans_and_examples():
    text = build_contract_prompt("dsl")
    assert "Grammar: <op> <target>[count] key=value ..." in text
    assert "Bans: no trailing punctuation, no standalone symbols, no JSON, one line only." in text
    assert "Examples:" in text


def test_contract_builder_structured_is_minimal_json_only():
    text = build_contract_prompt("structured")
    assert text == "Return JSON only. Match the requested schema exactly."


def test_decide_structured_recovery_matrix():
    assert decide_structured_recovery(
        schema_failed=True, json_failed=False, strict=True, fallback_enabled=True
    ) == "retry-json"
    assert decide_structured_recovery(
        schema_failed=True, json_failed=True, strict=True, fallback_enabled=True
    ) == "fail-strict"
    assert decide_structured_recovery(
        schema_failed=True, json_failed=True, strict=False, fallback_enabled=True
    ) == "fallback-dsl"


def test_build_transcript_record_shape_and_json_serializable():
    record = build_transcript_record(
        side="A",
        model="demo",
        mode="structured",
        request_mode="structured-schema",
        raw='{"op":"gen","target":"txt"}',
        parsed={"op": "gen", "target": "txt", "count": 1, "params": {}},
        dsl="gen txt",
        error=None,
        retry=0,
        elapsed_ms=12,
        timeout_s=180,
        keep_alive_s=300,
    )
    assert set(record) == {
        "ts",
        "side",
        "model",
        "mode",
        "request_mode",
        "raw",
        "parsed",
        "dsl",
        "error",
        "retry",
        "elapsed_ms",
        "timeout_s",
        "keep_alive_s",
    }
    assert record["request_mode"] == "structured-schema"
    assert record["elapsed_ms"] == 12
    json.dumps(record, sort_keys=True)
