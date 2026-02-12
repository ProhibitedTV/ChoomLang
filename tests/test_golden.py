import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from choomlang import cli

GOLDEN_DIR = Path(__file__).parent / "golden"
CASES_PATH = GOLDEN_DIR / "dsl_cases.txt"
FMT_PATH = GOLDEN_DIR / "expected_fmt.txt"
SCHEMA_PATH = GOLDEN_DIR / "schema.json"


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(args)
    return code, out.getvalue(), err.getvalue()


def _load_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for raw_line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        status, dsl = [part.strip() for part in line.split("|", 1)]
        if status not in {"VALID", "INVALID"}:
            raise ValueError(f"invalid status in {CASES_PATH}: {status!r}")
        cases.append((status, dsl))
    return cases


def _normalize_json_text(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def _regen_enabled() -> bool:
    return os.environ.get("REGEN_GOLDENS") == "1"


def test_golden_validate_accepts_valid_cases_only():
    valid_cases = [dsl for status, dsl in _load_cases() if status == "VALID"]
    assert valid_cases, "expected at least one VALID case"

    for dsl in valid_cases:
        code, out, err = _run_cli(["validate", dsl])
        assert code == 0, f"expected VALID case to pass: {dsl}\nerr={err}"
        assert out.strip() == "ok"


@pytest.mark.parametrize(
    "dsl",
    [dsl for status, dsl in _load_cases() if status == "INVALID"],
)
def test_golden_validate_rejects_invalid_cases(dsl: str):
    code, _out, _err = _run_cli(["validate", dsl])
    assert code == 2


def test_golden_fmt_matches_expected_file():
    valid_cases = [dsl for status, dsl in _load_cases() if status == "VALID"]
    fmt_outputs = []
    for dsl in valid_cases:
        code, out, err = _run_cli(["fmt", dsl])
        assert code == 0, f"fmt failed for {dsl}: {err}"
        fmt_outputs.append(out.rstrip("\n"))

    actual = "\n".join(fmt_outputs) + "\n"

    if _regen_enabled():
        FMT_PATH.write_text(actual, encoding="utf-8")

    expected = FMT_PATH.read_text(encoding="utf-8")
    assert actual == expected


def test_golden_schema_matches_expected_file():
    code, out, err = _run_cli(["schema"])
    assert code == 0, err
    actual = _normalize_json_text(out)

    if _regen_enabled():
        SCHEMA_PATH.write_text(actual, encoding="utf-8")

    expected = _normalize_json_text(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert actual == expected
