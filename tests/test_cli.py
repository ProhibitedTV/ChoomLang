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


def test_cli_schema_strict_contains_enum_only(capsys):
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
    assert payload["properties"]["op"] == {"$ref": "#/$defs/knownOp", "description": "Canonical operation name."}
    assert payload["properties"]["target"] == {"$ref": "#/$defs/knownTarget", "description": "Canonical target domain."}


def test_cli_schema_permissive_allows_additional_strings(capsys):
    code = main(["schema", "--mode", "permissive"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert "anyOf" in payload["properties"]["op"]
    assert payload["properties"]["op"]["anyOf"][1] == {"type": "string"}
    assert "anyOf" in payload["properties"]["target"]


def test_cli_guard_prompt_default_and_targeted(capsys):
    code = main(["guard"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "Grammar: <op> <target>[count] key=value ..." in out
    assert "Bans: no JSON, no trailing punctuation, no standalone symbols." in out

    code = main(["guard", "--error", "invalid header", "--previous", "hello"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "Error: invalid header" in out
    assert "Previous reply:" in out


def test_cli_validate_lenient_allows_trailing_dot(capsys):
    code = main(["validate", "ping txt .", "--lenient"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "ok"


def test_cli_fmt_lenient_allows_trailing_dot(capsys):
    code = main(["fmt", "ping txt .", "--lenient"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "healthcheck txt"


def test_cli_completion_default_shell(monkeypatch, capsys):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    code = main(["completion"])
    out = capsys.readouterr().out
    assert code == 0
    assert "#compdef choom" in out


def test_cli_completion_powershell(capsys):
    code = main(["completion", "powershell"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Register-ArgumentCompleter" in out


def test_cli_validate_suggests_missing_equals(capsys):
    code = main(["validate", "gen txt mood"])
    err = capsys.readouterr().err
    assert code == 2
    assert "did you mean mood=<value>?" in err


def test_cli_validate_suggests_lenient_for_trailing_dot(capsys):
    code = main(["validate", "ping txt ."])
    err = capsys.readouterr().err
    assert code == 2
    assert "try --lenient" in err


def test_cli_validate_warns_unknown_op_target(capsys):
    code = main(["validate", "invent unknown k=v"])
    captured = capsys.readouterr()
    assert code == 0
    assert "unknown op 'invent'" in captured.err
    assert "unknown target 'unknown'" in captured.err


def test_cli_demo_shortcut(monkeypatch, capsys):
    import choomlang.cli as cli

    class DummyClient:
        def __init__(self, timeout, keep_alive):
            self.timeout = timeout
            self.keep_alive = keep_alive

    captured = {}

    def fake_run_relay(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(cli, "OllamaClient", DummyClient)
    monkeypatch.setattr(cli, "run_relay", fake_run_relay)

    code = cli.main(["demo"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Relay Demo (v0.6)" in out
    assert captured["a_model"] == "llama3.2:latest"
    assert captured["b_model"] == "qwen2.5:latest"
    assert captured["turns"] == 4
    assert captured["structured"] is True
    assert captured["log_path"] == "choom_demo.jsonl"
