import json

import pytest

from choomlang.errors import RunError
from choomlang.runner import RunnerConfig, run_script


def test_run_script_creates_workdir_state_and_transcript(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=echo id=first\n", encoding="utf-8")

    workdir = tmp_path / "run"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True))

    assert len(outputs) == 1
    assert (workdir / "artifacts").is_dir()
    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert state["first"] == '{"id": "first"}'

    lines = (workdir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {
        "ts",
        "step",
        "dsl",
        "payload",
        "status",
        "elapsed_ms",
        "output",
        "stored_id",
        "error",
    }
    assert record["status"] == "success"


def test_run_script_interpolates_from_state_and_persists(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=echo id=a\n"
        "toolcall tool name=echo msg=@a id=b\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True))

    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert "id" in state["b"]
    assert "@a" not in state["b"]


def test_run_script_missing_interpolation_errors_or_skips_in_dry_run(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=echo msg=@missing\n", encoding="utf-8")

    workdir_error = tmp_path / "error"
    with pytest.raises(RunError, match="missing interpolation key"):
        run_script(str(script), config=RunnerConfig(workdir=str(workdir_error), dry_run=False))

    workdir_dry = tmp_path / "dry"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir_dry), dry_run=True))
    assert outputs == ["line 1: skipped (missing interpolation key(s): missing)"]
    record = json.loads((workdir_dry / "transcript.jsonl").read_text(encoding="utf-8").strip())
    assert record["status"] == "skipped"


def test_run_script_resume_uses_transcript_completed_steps(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=echo id=one\n"
        "toolcall tool name=echo id=two\n"
        "toolcall tool name=echo id=three\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True, max_steps=2))
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True, resume=True))

    assert len(outputs) == 1
    assert '"id": "three"' in outputs[0]


def test_run_script_enforces_toolcall_contract(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("gen txt prompt=hello\n", encoding="utf-8")

    workdir = tmp_path / "run"
    with pytest.raises(RunError, match="requires canonical"):
        run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))


def test_run_script_requires_params_name(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool trace=test\n", encoding="utf-8")

    workdir = tmp_path / "run"
    with pytest.raises(RunError, match="params.name"):
        run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))
