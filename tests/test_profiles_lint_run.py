import json

from choomlang import __version__
from choomlang.cli import main
from choomlang.profiles import (
    ProfileError,
    apply_profile_to_dsl,
    list_profiles,
    search_profiles,
    validate_profile_payload,
)
from choomlang.errors import RunError
from choomlang.run import run_toolcall


def test_version_is_0_10_2():
    assert __version__ == "0.10.2"


def test_profile_schema_validation_helper_valid_and_invalid():
    validate_profile_payload(
        {
            "name": "demo",
            "tags": ["text", "example"],
            "description": "example",
            "defaults": {"style": "plain", "count": 2, "safe": True, "note": None},
        },
        source="memory",
    )

    try:
        validate_profile_payload(
            {
                "name": "bad",
                "defaults": {"nested": {"bad": "value"}},
            },
            source="memory",
        )
    except ProfileError as exc:
        assert "string|number|boolean|null" in str(exc)
    else:
        raise AssertionError("expected validation failure")


def test_profile_list_and_apply_deterministic(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "demo.json").write_text(
        """{
  "name": "demo",
  "tags": ["image", "cinematic"],
  "defaults": {"res": "1920x1080", "style": "cinematic"},
  "notes": "demo"
}
""",
        encoding="utf-8",
    )

    names = list_profiles(profiles_dir=profile_dir)
    assert names == ["demo"]
    result = apply_profile_to_dsl(
        "demo",
        "gen img[2] prompt=city",
        profiles_dir=profile_dir,
        overrides={"style": "retro", "seed": 12},
    )
    assert result == "gen img[2] prompt=city res=1920x1080 seed=12 style=retro"


def test_profile_apply_preserves_op_target_count(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "demo.json").write_text(
        '{"name":"demo","defaults":{"tone":"calm"}}',
        encoding="utf-8",
    )

    result = apply_profile_to_dsl("demo", "summarize txt[3] prompt=hello", profiles_dir=profile_dir)
    assert result.startswith("summarize txt[3] ")


def test_profile_search_and_tag_filter(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "wallpaper.json").write_text(
        '{"name":"wallpaper","tags":["Image","cinematic"],"description":"Wide wallpaper","defaults":{"res":"1920x1080"}}',
        encoding="utf-8",
    )
    (profile_dir / "brief_writer.json").write_text(
        '{"name":"brief_writer","tags":["text"],"description":"Concise writing","defaults":{"tone":"clear"}}',
        encoding="utf-8",
    )

    assert list_profiles(profiles_dir=profile_dir, tag="image") == ["wallpaper"]
    assert search_profiles("CONCISE", profiles_dir=profile_dir) == ["brief_writer"]


def test_cli_profile_show(capsys):
    code = main(["profile", "show", "classify_basic"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["name"] == "classify_basic"


def test_cli_profile_list_skips_invalid(capsys, tmp_path, monkeypatch):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "valid.json").write_text('{"name":"valid","defaults":{"x":1}}', encoding="utf-8")
    (profile_dir / "broken.json").write_text('{"name":"broken","defaults":{"x":{"bad":1}}}', encoding="utf-8")

    import choomlang.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "_profiles_dir", lambda profiles_dir=None: profile_dir)
    code = main(["profile", "list"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "valid"
    assert "skipping invalid profile" in captured.err


def test_cli_profile_search_and_tag(capsys):
    code = main(["profile", "list", "--tag", "tool"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert "echo_tool" in out
    assert "write_file_safe" in out

    code = main(["profile", "search", "portrait"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert out == ["photoreal_portrait"]


def test_cli_profile_apply_set_overrides(capsys):
    code = main(
        [
            "profile",
            "apply",
            "wallpaper",
            "gen img[2] prompt=city",
            "--set",
            "style=retro",
            "--set",
            "seed=7",
        ]
    )
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "gen img[2] prompt=city quality=high res=1920x1080 seed=7 style=retro"


def test_cli_profile_apply_invalid_set_token(capsys):
    code = main(["profile", "apply", "wallpaper", "gen img", "--set", "badtoken"])
    err = capsys.readouterr().err
    assert code == 2
    assert "expected key=value" in err


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
    assert msg == '{"trace": "test"}'

    out_dir = tmp_path / "out"
    msg = run_toolcall(
        "toolcall tool name=write_file path=notes/a.txt text=hello",
        out_dir=str(out_dir),
        dry_run=False,
    )
    assert msg == "notes/a.txt"
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
        assert "path traversal" in str(exc)
    else:
        raise AssertionError("expected path traversal RunError")


def test_cli_run_dry_run(capsys, tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=echo id=123\n", encoding="utf-8")

    code = main(["run", str(script), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "line 1:" in out
    assert '{"id": 123}' in out


def test_run_toolcall_read_mkdir_and_list_dir(tmp_path):
    out_dir = tmp_path / "out"
    created = run_toolcall("toolcall tool name=mkdir path=docs", out_dir=str(out_dir), dry_run=False)
    assert created == "docs"

    run_toolcall(
        "toolcall tool name=write_file path=docs/b.txt text=two",
        out_dir=str(out_dir),
        dry_run=False,
    )
    run_toolcall(
        "toolcall tool name=write_file path=docs/a.txt text=one",
        out_dir=str(out_dir),
        dry_run=False,
    )

    listing = run_toolcall("toolcall tool name=list_dir path=docs", out_dir=str(out_dir), dry_run=False)
    assert listing == '["a.txt","b.txt"]'

    content = run_toolcall("toolcall tool name=read_file path=docs/a.txt", out_dir=str(out_dir), dry_run=False)
    assert content == "one"


def test_run_blocks_absolute_paths(tmp_path):
    out_dir = tmp_path / "out"
    with_absolute = "/tmp/escape.txt"
    try:
        run_toolcall(
            f"toolcall tool name=write_file path={with_absolute} text=hello",
            out_dir=str(out_dir),
            dry_run=False,
        )
    except RunError as exc:
        assert "absolute paths" in str(exc)
    else:
        raise AssertionError("expected absolute path RunError")
