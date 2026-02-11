import json

from choomlang.cli import main


def test_cli_translate(capsys):
    code = main(["translate", "jack img[2] style=studio res=1024x1024"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["op"] == "gen"
    assert payload["count"] == 2


def test_cli_reverse_translate(capsys):
    text = '{"op":"gen","target":"img","count":2,"params":{"style":"studio","res":"1024x1024"}}'
    code = main(["translate", "--reverse", text])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "gen img[2] res=1024x1024 style=studio"


def test_cli_teach(capsys):
    code = main(["teach", "jack img[1] style=studio"])
    out = capsys.readouterr().out
    assert code == 0
    assert "alias -> gen" in out
