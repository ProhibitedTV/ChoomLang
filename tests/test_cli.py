import json

from choomlang.cli import main


def test_cli_translate(capsys):
    code = main(["translate", "jack img[2] style=studio res=1024x1024"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["op"] == "gen"
    assert payload["count"] == 2


def test_cli_translate_autodetect_json_to_dsl(capsys):
    text = '{"op":"gen","target":"img","count":2,"params":{"style":"studio","res":"1024x1024"}}'
    code = main(["translate", text])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "gen img[2] res=1024x1024 style=studio"


def test_cli_translate_compact_json(capsys):
    code = main(["translate", "gen txt tone=noir", "--compact"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == '{"count":1,"op":"gen","params":{"tone":"noir"},"target":"txt"}'


def test_cli_reverse_translate(capsys):
    text = '{"op":"gen","target":"img","count":2,"params":{"style":"studio","res":"1024x1024"}}'
    code = main(["translate", "--reverse", text])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "gen img[2] res=1024x1024 style=studio"


def test_cli_validate_success(capsys):
    code = main(["validate", "gen txt tone=noir"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "ok"


def test_cli_validate_error(capsys):
    code = main(["validate", "not"])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err


def test_cli_translate_stdin(monkeypatch, capsys):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("gen txt mood=calm\n"))
    code = main(["translate"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["params"]["mood"] == "calm"


def test_cli_validate_stdin(monkeypatch, capsys):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("gen txt mood=calm\n"))
    code = main(["validate"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "ok"


def test_cli_teach(capsys):
    code = main(["teach", "jack img[1] style=studio"])
    out = capsys.readouterr().out
    assert code == 0
    assert "alias -> gen" in out


def test_cli_fmt_normalizes_alias_sort_and_quotes(capsys):
    code = main(["fmt", 'jack txt[1] z=2 a="two words"'])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == 'gen txt a="two words" z=2'


def test_cli_fmt_stdin(monkeypatch, capsys):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO('jack txt mood="night city"\n'))
    code = main(["fmt"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == 'gen txt mood="night city"'


def test_cli_script_jsonl_ignores_comments_and_blanks(capsys, tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "\n"
        "# full comment\n"
        "jack img[1] style=studio  # inline\n"
        'scan txt label="#not-comment" # trailing comment\n',
        encoding="utf-8",
    )

    code = main(["script", str(script)])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert out == [
        '{"count":1,"op":"gen","params":{"style":"studio"},"target":"img"}',
        '{"count":1,"op":"classify","params":{"label":"#not-comment"},"target":"txt"}',
    ]


def test_cli_script_dsl_continue_reports_errors(capsys, tmp_path):
    script = tmp_path / "bad.choom"
    script.write_text(
        "jack txt mood=ok\n"
        "broken\n"
        "scan txt tag=green\n",
        encoding="utf-8",
    )

    code = main(["script", str(script), "--to", "dsl", "--continue"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out.strip().splitlines() == ["gen txt mood=ok", "classify txt tag=green"]
    assert "error: line 2:" in captured.err


def test_cli_schema_contains_known_enums(capsys):
    code = main(["schema"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["$defs"]["knownOp"]["enum"] == [
        "gen",
        "classify",
        "summarize",
        "plan",
        "healthcheck",
        "toolcall",
        "forward",
    ]
    assert payload["$defs"]["knownTarget"]["enum"] == ["img", "txt", "aud", "vid", "vec", "tool"]


def test_cli_guard_prompt_default_and_targeted(capsys):
    code = main(["guard"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "Reply with exactly one valid ChoomLang DSL line and no extra text." in out

    code = main(["guard", "--error", "invalid header", "--previous", "hello"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "Error: invalid header" in out
    assert "Previous reply:" in out
