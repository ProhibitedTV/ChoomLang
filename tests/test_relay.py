import pytest

from choomlang.relay import RelayError, strict_validate_with_retry


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
    assert line == "scan txt confidence=true"
    assert payload["op"] == "classify"


def test_strict_validate_with_retry_fails_after_bad_retry():
    def retry(_: str) -> str:
        return "still not dsl"

    with pytest.raises(RelayError, match="after retry"):
        strict_validate_with_retry("nope", strict=True, retry=retry)
