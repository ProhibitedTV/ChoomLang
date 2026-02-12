from pathlib import Path

from choomlang.dsl import parse_dsl


def _iter_example_lines() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for path in sorted(Path("examples").glob("*.choom")):
        text = path.read_text(encoding="utf-8")
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append((str(path), line_no, line))
    return rows


def test_examples_all_choom_lines_parse_as_valid_dsl():
    lines = _iter_example_lines()
    assert lines, "expected at least one .choom line to lint"

    for path, line_no, line in lines:
        try:
            parse_dsl(line)
        except Exception as exc:  # pragma: no cover - assertion path only
            raise AssertionError(f"{path}:{line_no} failed DSL parse: {line}\n{exc}") from exc
