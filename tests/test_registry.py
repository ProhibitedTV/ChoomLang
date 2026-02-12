import pytest

from choomlang.registry import normalize_op, validate_payload


def test_validate_payload_strict_rejects_unknown_op():
    with pytest.raises(ValueError, match="field op='success'"):
        validate_payload({"op": "success", "target": "txt", "count": 1, "params": {}}, strict_ops=True)


def test_validate_payload_strict_rejects_unknown_target():
    with pytest.raises(ValueError, match="field target='ping'"):
        validate_payload({"op": "gen", "target": "ping", "count": 1, "params": {}}, strict_targets=True)


def test_normalize_op_aliases():
    assert normalize_op("jack") == "gen"
    assert normalize_op("scan") == "classify"
