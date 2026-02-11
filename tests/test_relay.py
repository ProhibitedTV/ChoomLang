import pytest

from choomlang.relay import (
    RelayError,
    build_transcript_record,
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


def test_build_transcript_record_shape():
    record = build_transcript_record(
        side="A",
        model="demo",
        mode="structured",
        raw='{"op":"gen","target":"txt"}',
        parsed={"op": "gen", "target": "txt", "count": 1, "params": {}},
        dsl="gen txt",
        error=None,
        retry=0,
    )
    assert set(record) == {"ts", "side", "model", "mode", "raw", "parsed", "dsl", "error", "retry"}
    assert record["side"] == "A"
    assert record["mode"] == "structured"
