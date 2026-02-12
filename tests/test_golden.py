import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from choomlang import cli

GOLDEN_DIR = Path(__file__).parent / "golden"
VALID_DSL_PATH = GOLDEN_DIR / "dsl_valid.txt"
INVALID_DSL_PATH = GOLDEN_DIR / "dsl_invalid.txt"
FMT_EXPECTED_PATH = GOLDEN_DIR / "fmt_expected.txt"
SCHEMA_EXPECTED_PATH = GOLDEN_DIR / "schema_expected.json"


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(args)
    return code, out.getvalue(), err.getvalue()


def _load_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _normalize_json_text(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def _regen_enabled() -> bool:
    return os.environ.get("REGEN_GOLDENS") == "1"


def test_golden_validate_and_fmt_for_valid_cases():
    valid_cases = _load_lines(VALID_DSL_PATH)
    assert valid_cases, "expected at least one valid DSL case"

    fmt_outputs = []
    for dsl in valid_cases:
        validate_code, validate_out, validate_err = _run_cli(["validate", dsl])
        assert validate_code == 0, (
            f"expected VALID case to pass: {dsl}\nerr={validate_err}"
        )
        assert validate_out.strip() == "ok"

        fmt_code, fmt_out, fmt_err = _run_cli(["fmt", dsl])
        assert fmt_code == 0, f"fmt failed for {dsl}: {fmt_err}"
        fmt_outputs.append(fmt_out.rstrip("\n"))

    actual_fmt = "\n".join(fmt_outputs) + "\n"

    if _regen_enabled():
        FMT_EXPECTED_PATH.write_text(actual_fmt, encoding="utf-8", newline="\n")

    expected_fmt = FMT_EXPECTED_PATH.read_text(encoding="utf-8")
    assert actual_fmt == expected_fmt


@pytest.mark.parametrize("dsl", _load_lines(INVALID_DSL_PATH))
def test_golden_validate_rejects_invalid_cases(dsl: str):
    code, _out, _err = _run_cli(["validate", dsl])
    assert code == 2


def test_golden_schema_matches_expected_file():
    code, out, err = _run_cli(["schema"])
    assert code == 0, err
    actual_schema = _normalize_json_text(out)

    if _regen_enabled():
        SCHEMA_EXPECTED_PATH.write_text(
            actual_schema,
            encoding="utf-8",
            newline="\n",
        )

    expected_schema = _normalize_json_text(
        SCHEMA_EXPECTED_PATH.read_text(encoding="utf-8")
    )
    assert actual_schema == expected_schema
