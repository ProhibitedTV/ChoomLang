import json

from choomlang import __version__
from choomlang.cli import main
from choomlang.profiles import apply_profile_to_dsl, list_profiles
from choomlang.run import run_toolcall, RunError


def test_version_is_0_8_0():
    assert __version__ == "0.8.0"


def test_profile_list_and_apply_deterministic(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "demo.json").write_text(
        """{
  "name": "demo",
  "defaults": {"res": "1920x1080", "style": "cyberpunk"},
  "notes": "demo"
}
""",
        encoding="utf-8",
    )

    names = list_profiles(profiles_dir=profile_dir)
    assert names == ["demo"]
    result = apply_profile_to_dsl(
        "demo",
        'gen img prompt="city" style=retro',
        profiles_dir=profile_dir,
    )
    assert result == 'gen img prompt=city res=1920x1080 style=retro'


def test_cli_profile_show(capsys):
    code = main(["profile", "show", "osint_basic"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["name"] == "osint_basic"


def test_lint_warning_exit_codes(capsys):
    code = main(["lint", "jack txt tone=noir"])
    err = capsys.readouterr().err
    assert code == 1
    assert "non-canonical" in err

    code = main(["lint", "gen txt tone=noir"])
    assert code == 0


def test_lint_strict_unknown_registry_warnings(capsys):
    code = main(["lint", "newop txt x=1", "--strict-ops"])
    err = capsys.readouterr().err
    assert code == 1
    assert "unknown op" in err


def test_run_toolcall_dry_run_and_write_file(tmp_path):
    msg = run_toolcall("toolcall tool name=echo trace=test", dry_run=True)
    assert "dry-run" in msg

    out_dir = tmp_path / "out"
    msg = run_toolcall(
        "toolcall tool name=write_file path=notes/a.txt text=hello",
        out_dir=str(out_dir),
        dry_run=False,
    )
    assert "executed" in msg
    assert (out_dir / "notes" / "a.txt").read_text(encoding="utf-8") == "hello"


def test_run_blocks_path_traversal(tmp_path):
    out_dir = tmp_path / "out"
    try:
        run_toolcall(
            "toolcall tool name=write_file path=../escape.txt text=hello",
            out_dir=str(out_dir),
            dry_run=False,
        )
    except RunError as exc:
        assert "unsafe path" in str(exc)
    else:
        raise AssertionError("expected path traversal RunError")


def test_cli_run_dry_run(capsys):
    code = main(["run", "toolcall tool name=echo id=123", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "dry-run" in out
