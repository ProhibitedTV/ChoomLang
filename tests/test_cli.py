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
    assert payload["$defs"]["knownTarget"]["enum"] == ["img", "txt", "aud", "vid", "vec", "tool", "script"]
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


def test_cli_run_uses_filtered_script_lines(capsys, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text(
        "\n"
        "# comment\n"
        "toolcall tool name=echo id=1\n"
        "\n"
        "toolcall tool name=echo id=2 # inline comment\n",
        encoding="utf-8",
    )

    code = main(["run", str(script), "--dry-run"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert len(out) == 2
    assert out[0].startswith("line 3:")
    assert out[1].startswith("line 5:")


def test_cli_run_resume_and_max_steps(capsys, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text(
        "toolcall tool name=echo id=1\n"
        "toolcall tool name=echo id=2\n"
        "toolcall tool name=echo id=3\n",
        encoding="utf-8",
    )

    code = main(["run", str(script), "--dry-run", "--resume", "2", "--max-steps", "1"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert len(out) == 1
    assert '"id": 2' in out[0]




def test_cli_run_a1111_url_precedence_cli_over_env(monkeypatch, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_script(script_path, **kwargs):
        captured["script_path"] = script_path
        captured.update(kwargs)
        return []

    monkeypatch.setenv("CHOOM_A1111_URL", "http://env:7860")
    monkeypatch.setattr("choomlang.cli.run_script", fake_run_script)

    code = main(["run", str(script), "--a1111-url", "http://cli:7860"])

    assert code == 0
    assert captured["script_path"] == str(script)
    assert captured["a1111_url"] == "http://cli:7860"


def test_cli_run_a1111_url_precedence_env_over_default(monkeypatch, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_script(script_path, **kwargs):
        captured["script_path"] = script_path
        captured.update(kwargs)
        return []

    monkeypatch.setenv("CHOOM_A1111_URL", "http://env:7860")
    monkeypatch.setattr("choomlang.cli.run_script", fake_run_script)

    code = main(["run", str(script)])

    assert code == 0
    assert captured["a1111_url"] == "http://env:7860"


def test_cli_run_a1111_timeout_precedence_cli_over_env(monkeypatch, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_script(script_path, **kwargs):
        _ = script_path
        captured.update(kwargs)
        return []

    monkeypatch.setenv("CHOOM_A1111_TIMEOUT", "22")
    monkeypatch.setattr("choomlang.cli.run_script", fake_run_script)

    code = main(["run", str(script), "--a1111-timeout", "4.5", "--cancel-on-timeout"])

    assert code == 0
    assert captured["a1111_timeout"] == 4.5
    assert captured["cancel_on_timeout"] is True


def test_cli_run_a1111_timeout_precedence_env_over_timeout(monkeypatch, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_script(script_path, **kwargs):
        _ = script_path
        captured.update(kwargs)
        return []

    monkeypatch.setenv("CHOOM_A1111_TIMEOUT", "11")
    monkeypatch.setattr("choomlang.cli.run_script", fake_run_script)

    code = main(["run", str(script), "--timeout", "99"])

    assert code == 0
    assert captured["a1111_timeout"] == 11.0


def test_cli_run_a1111_url_default_when_env_absent(monkeypatch, tmp_path):
    script = tmp_path / "run.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_script(script_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.delenv("CHOOM_A1111_URL", raising=False)
    monkeypatch.setattr("choomlang.cli.run_script", fake_run_script)

    code = main(["run", str(script)])

    assert code == 0
    assert captured["a1111_url"] == "http://127.0.0.1:7860"

def test_cli_run_reports_actionable_errors(capsys, tmp_path):
    bad_parse = tmp_path / "bad_parse.choom"
    bad_parse.write_text("broken\n", encoding="utf-8")

    code = main(["run", str(bad_parse)])
    err = capsys.readouterr().err
    assert code == 2
    assert "bad_parse.choom:1: parse error:" in err

    bad_runtime = tmp_path / "bad_runtime.choom"
    bad_runtime.write_text("toolcall tool name=unknown\n", encoding="utf-8")

    code = main(["run", str(bad_runtime)])
    err = capsys.readouterr().err
    assert code == 2
    assert "bad_runtime.choom:1:" in err
    assert "dsl='toolcall tool name=unknown'" in err


def test_cli_run_resume_out_of_range_is_clear_and_nonzero(capsys, tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=echo\n", encoding="utf-8")

    code = main(["run", str(script), "--resume", "2"])
    err = capsys.readouterr().err
    assert code == 2
    assert "--resume out of range" in err
    assert "script has 1 step(s)" in err


def test_cli_validate_script_command(capsys, tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("gen txt prompt=hello\n", encoding="utf-8")

    code = main(["validate-script", str(script)])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "ok"


def test_cli_script_validate_only(capsys, tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("gen txt prompt=hello\n", encoding="utf-8")

    code = main(["script", str(script), "--validate-only"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "ok"
