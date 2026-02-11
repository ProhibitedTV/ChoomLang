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
