import json

import pytest

from choomlang.protocol import build_contract_prompt
from choomlang.relay import (
    RelayError,
    build_chat_request,
    build_ping_messages,
    build_transcript_record,
    decide_structured_recovery,
    parse_structured_reply,
    run_relay,
    strict_validate_with_retry,
    suggest_model_names,
    summarize_transcript,
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




def test_parse_structured_reply_strict_rejects_unknown_op_target():
    with pytest.raises(RelayError, match="field op='success'"):
        parse_structured_reply('{"op":"success","target":"txt"}')

    with pytest.raises(RelayError, match="field target='ping'"):
        parse_structured_reply('{"op":"gen","target":"ping"}')

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
    assert decide_structured_recovery(
        schema_failed=True, json_failed=False, strict=False, fallback_enabled=False
    ) == "fail-no-fallback"


def test_build_chat_request_for_structured_mode_enforces_stream_false():
    payload = build_chat_request(
        model="llama",
        messages=[{"role": "user", "content": "hello"}],
        seed=42,
        response_format="json",
        keep_alive=300,
    )
    assert payload == {
        "model": "llama",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "options": {"seed": 42},
        "keep_alive": 300,
        "format": "json",
    }


def test_build_ping_messages_contains_canonical_ping_json():
    messages = build_ping_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert '"op": "healthcheck"' in messages[0]["content"]


def test_build_transcript_record_shape_and_json_serializable():
    record = build_transcript_record(
        request_id=7,
        side="A",
        model="demo",
        mode="structured",
        stage="structured-schema",
        request_mode="structured-schema",
        http_status=200,
        raw='{"op":"gen","target":"txt"}',
        parsed={"op": "gen", "target": "txt", "count": 1, "params": {}},
        dsl="gen txt",
        error=None,
        retry=1,
        elapsed_ms=12,
        timeout_s=180,
        keep_alive_s=300,
        fallback_reason="schema-timeout",
    )
    assert set(record) == {
        "ts",
        "request_id",
        "side",
        "model",
        "mode",
        "stage",
        "request_mode",
        "http_status",
        "raw",
        "parsed",
        "dsl",
        "error",
        "retry",
        "elapsed_ms",
        "timeout_s",
        "keep_alive_s",
        "fallback_reason",
        "invalid_fields",
        "raw_json_text",
        "repeat_prevented",
    }
    assert record["request_mode"] == "structured-schema"
    assert record["stage"] == "structured-schema"
    assert record["elapsed_ms"] == 12
    json.dumps(record, sort_keys=True)


def test_summarize_transcript_aggregates_retries_fallbacks_and_latency():
    summary = summarize_transcript(
        [
            {
                "stage": "structured-schema",
                "elapsed_ms": 100,
                "retry": 0,
                "fallback_reason": None,
            },
            {
                "stage": "structured-json",
                "elapsed_ms": 200,
                "retry": 1,
                "fallback_reason": "schema-failed:timeout",
            },
            {
                "stage": "structured-json",
                "elapsed_ms": 300,
                "retry": 0,
                "fallback_reason": None,
            },
        ]
    )
    assert summary["total_turns"] == 3
    assert summary["retries"] == 1
    assert summary["repeats_prevented"] == 0
    assert summary["fallbacks_by_stage"] == {"structured-json": 1}
    assert summary["elapsed_ms_by_stage"]["structured-json"] == {
        "avg_ms": 250.0,
        "median_ms": 250.0,
    }


def test_suggest_model_names_returns_close_matches():
    matches = suggest_model_names(
        "llama3.2:lates",
        ["llama3.2:latest", "qwen2.5:latest", "mistral:latest"],
    )
    assert matches
    assert matches[0] == "llama3.2:latest"


def test_parse_structured_reply_error_message_is_diagnostic():
    with pytest.raises(RelayError, match="valid JSON"):
        parse_structured_reply("not-json")


def test_parse_structured_reply_requires_params_text_for_gen_script():
    with pytest.raises(RelayError, match="params.text is required string"):
        parse_structured_reply('{"op":"gen","target":"script","params":{}}')


def test_parse_structured_reply_rejects_prompt_for_gen_script():
    with pytest.raises(RelayError, match="params.prompt is not allowed"):
        parse_structured_reply('{"op":"gen","target":"script","params":{"text":"gen txt prompt=ok","prompt":"bad"}}')


def test_parse_structured_reply_validates_script_text_for_gen_script():
    with pytest.raises(RelayError, match="must be a valid multi-line ChoomLang script"):
        parse_structured_reply('{"op":"gen","target":"script","params":{"text":"oops"}}')

    payload, dsl = parse_structured_reply(
        '{"op":"gen","target":"script","params":{"text":"gen txt prompt=hello\\nclassify txt label=ok"}}'
    )
    assert payload["params"]["text"].startswith("gen txt")
    assert dsl.startswith('gen script text="gen txt prompt=hello')
    assert 'classify txt label=ok"' in dsl


def test_run_relay_structured_no_repeat_retries_and_succeeds(capsys):
    class MockClient:
        def __init__(self):
            self.timeout = 180.0
            self.keep_alive = 300.0
            self.calls = []
            self.outputs = [
                '{"op":"gen","target":"txt"}',
                '{"op":"plan","target":"txt","params":{"step":"next"}}',
                '{"op":"summarize","target":"txt","params":{"topic":"progress"}}',
            ]

        def chat(self, model, messages, seed=None, response_format=None):
            self.calls.append({"model": model, "messages": messages, "response_format": response_format})
            return self.outputs[len(self.calls) - 1], 5, 200

    client = MockClient()
    transcript = run_relay(
        client=client,
        a_model="a",
        b_model="b",
        turns=1,
        structured=True,
        use_schema=False,
        strict=True,
        start="gen txt",
    )

    assert len(transcript) == 2
    assert transcript[0][2]["op"] == "plan"
    assert len(client.calls) == 3
    assert "Do not repeat the previous line; advance the workflow." in client.calls[1]["messages"][-1]["content"]

    err = capsys.readouterr().err
    assert "repeats_prevented=1" in err


def test_run_relay_structured_allow_repeat_allows_exact_repeat(capsys):
    class MockClient:
        def __init__(self):
            self.timeout = 180.0
            self.keep_alive = 300.0
            self.calls = []
            self.outputs = [
                '{"op":"gen","target":"txt"}',
                '{"op":"gen","target":"txt"}',
            ]

        def chat(self, model, messages, seed=None, response_format=None):
            self.calls.append({"model": model, "messages": messages, "response_format": response_format})
            return self.outputs[len(self.calls) - 1], 5, 200

    client = MockClient()
    transcript = run_relay(
        client=client,
        a_model="a",
        b_model="b",
        turns=1,
        structured=True,
        use_schema=False,
        strict=True,
        start="gen txt",
        no_repeat=False,
    )

    assert len(transcript) == 2
    assert transcript[0][2] == {"op": "gen", "target": "txt", "count": 1, "params": {}}
    assert len(client.calls) == 2
    err = capsys.readouterr().err
    assert "repeats_prevented=0" in err
