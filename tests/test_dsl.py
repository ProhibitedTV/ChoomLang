import pytest

from choomlang.dsl import DSLParseError, format_dsl, parse_dsl, serialize_dsl


def test_roundtrip_dsl_json_dsl():
    line = 'jack img[2] style=studio res=1024x1024 seed=42 prompt="neon city"'
    parsed = parse_dsl(line).to_json_dict()
    rebuilt = serialize_dsl(parsed)
    assert rebuilt == 'gen img[2] prompt="neon city" res=1024x1024 seed=42 style=studio'


def test_alias_normalization():
    parsed = parse_dsl("ghost txt length=short")
    assert parsed.op == "summarize"


@pytest.mark.parametrize(
    "token,expected",
    [
        ("n=42", 42),
        ("pi=3.14", 3.14),
        ("ok=true", True),
        ("no=false", False),
        ('note="hello world"', "hello world"),
        ("mode=cyberpunk", "cyberpunk"),
    ],
)
def test_type_coercion(token, expected):
    parsed = parse_dsl(f"gen txt {token}")
    key = token.split("=", 1)[0]
    assert parsed.params[key] == expected


def test_escaped_quotes_in_quoted_value():
    parsed = parse_dsl(r'gen txt text="he said \"yo\""')
    assert parsed.params["text"] == 'he said "yo"'


def test_invalid_header_error():
    with pytest.raises(DSLParseError, match="invalid header"):
        parse_dsl("gen")


def test_bad_count_error():
    with pytest.raises(DSLParseError, match="bad count"):
        parse_dsl("gen img[0]")


def test_malformed_kv_error():
    with pytest.raises(DSLParseError, match="malformed kv"):
        parse_dsl("gen img badtoken")


def test_unterminated_quote_error():
    with pytest.raises(DSLParseError, match="unterminated quote"):
        parse_dsl('gen txt msg="oops')


def test_format_dsl_normalizes_alias_order_and_count_omission():
    formatted = format_dsl('jack img[1] z=9 a=1')
    assert formatted == 'gen img a=1 z=9'


def test_format_dsl_stable_quoting_and_escape():
    formatted = format_dsl(r'gen txt note="he said \"yo\"" tag=safe')
    assert formatted == r'gen txt note="he said \"yo\"" tag=safe'


def test_format_dsl_quotes_when_needed():
    formatted = format_dsl('gen txt msg="two words" token=abc')
    assert formatted == 'gen txt msg="two words" token=abc'


def test_lenient_trailing_punctuation():
    with pytest.raises(DSLParseError):
        parse_dsl("ping txt .")

    parsed = parse_dsl("ping txt .", lenient=True)
    assert parsed.op == "healthcheck"
    assert parsed.target == "txt"


def test_format_dsl_lenient_trailing_punctuation():
    with pytest.raises(DSLParseError):
        format_dsl("gen txt .")

    assert format_dsl("gen txt .", lenient=True) == "gen txt"
