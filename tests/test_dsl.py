import pytest

from choomlang.dsl import DSLParseError, parse_dsl, serialize_dsl


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
