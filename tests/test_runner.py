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


def test_run_script_end_to_end_write_read_and_interpolate_id(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=write_file path=notes/hello.txt text=hello id=written_path\n"
        "toolcall tool name=read_file path=@written_path id=file_text\n"
        "toolcall tool name=echo msg=@file_text\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))

    assert outputs == [
        "line 1: notes/hello.txt",
        "line 2: hello",
        'line 3: {"msg": "hello"}',
    ]
    assert (workdir / "artifacts" / "notes" / "hello.txt").read_text(encoding="utf-8") == "hello"
    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert state["written_path"] == "notes/hello.txt"
    assert state["file_text"] == "hello"


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


def test_run_script_resume_seeded_state_and_transcript_continues_next_step_only(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=echo msg=first id=first\n"
        "toolcall tool name=echo msg=@first id=second\n"
        "toolcall tool name=echo msg=@second id=third\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "state.json").write_text('{"first":"first"}', encoding="utf-8")
    (workdir / "transcript.jsonl").write_text(
        "\n".join(
            [
                '{"status":"success","step":1}',
                '{"status":"success","step":2}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True, resume=True))

    assert outputs == ['line 3: skipped (missing interpolation key(s): second)']
    transcript_lines = (workdir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(transcript_lines) == 3
    appended = json.loads(transcript_lines[-1])
    assert appended["step"] == 3


def test_run_script_blocks_path_traversal_with_explicit_safety_error(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=write_file path=../x text=unsafe\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    with pytest.raises(RunError, match=r"runtime error: unsafe artifact path \(path traversal is not allowed\): ../x"):
        run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))


def test_run_script_dry_run_validates_and_skips_missing_interpolation_without_writing_files(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=write_file path=notes/file.txt text=hello\n"
        "toolcall tool name=read_file path=@missing\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=True))

    assert outputs == [
        "line 1: notes/file.txt",
        "line 2: skipped (missing interpolation key(s): missing)",
    ]
    transcript_lines = (workdir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(transcript_lines) == 2
    skipped = json.loads(transcript_lines[1])
    assert skipped["status"] == "skipped"
    assert skipped["error"] == "missing interpolation key(s): missing"
    assert not list((workdir / "artifacts").rglob("*"))


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




def test_run_script_passes_step_and_a1111_url_context_to_adapters(tmp_path, monkeypatch):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=echo id=first\n"
        "toolcall tool name=echo id=second\n",
        encoding="utf-8",
    )

    calls: list[dict[str, object]] = []

    def fake_run_adapter(name, params, artifacts_dir, dry_run, **kwargs):
        _ = artifacts_dir
        _ = dry_run
        calls.append({"name": name, "params": params, "context": kwargs.get("context")})
        return "ok"

    monkeypatch.setattr("choomlang.runner.run_adapter", fake_run_adapter)

    workdir = tmp_path / "run"
    outputs = run_script(
        str(script),
        config=RunnerConfig(workdir=str(workdir), dry_run=False, a1111_url="http://a1111:9000"),
    )

    assert outputs == ["line 1: ok", "line 2: ok"]
    assert calls == [
        {
            "name": "echo",
            "params": {"id": "first"},
            "context": {"step": 1, "a1111_url": "http://a1111:9000"},
        },
        {
            "name": "echo",
            "params": {"id": "second"},
            "context": {"step": 2, "a1111_url": "http://a1111:9000"},
        },
    ]

def test_run_script_ollama_chat_adapter_with_fake_client(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        'toolcall tool name=ollama_chat model=llama3.2 prompt="hello"\n',
        encoding="utf-8",
    )

    class FakeLLMClient:
        def __init__(self):
            self.calls = []

        def chat(self, model, *, prompt=None, messages=None, timeout=None, keep_alive=None):
            self.calls.append(
                {
                    "model": model,
                    "prompt": prompt,
                    "messages": messages,
                    "timeout": timeout,
                    "keep_alive": keep_alive,
                }
            )
            return "assistant says hi"

    fake = FakeLLMClient()
    workdir = tmp_path / "run"
    outputs = run_script(
        str(script),
        config=RunnerConfig(
            workdir=str(workdir),
            dry_run=False,
            timeout=12.5,
            keep_alive=45.0,
            llm_client=fake,
        ),
    )

    assert outputs == ["line 1: assistant says hi"]
    assert fake.calls == [
        {
            "model": "llama3.2",
            "prompt": "hello",
            "messages": None,
            "timeout": 12.5,
            "keep_alive": 45.0,
        }
    ]


def test_run_script_ollama_alias_accepts_messages_json_string(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        "toolcall tool name=ollama model=qwen2.5 "
        "messages='[{\"role\":\"user\",\"content\":\"ping\"}]'\n",
        encoding="utf-8",
    )


    class FakeLLMClient:
        def __init__(self):
            self.calls = []

        def chat(self, model, *, prompt=None, messages=None, timeout=None, keep_alive=None):
            self.calls.append({"model": model, "prompt": prompt, "messages": messages})
            return "pong"

    fake = FakeLLMClient()
    workdir = tmp_path / "run"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), llm_client=fake))

    assert outputs == ["line 1: pong"]
    assert fake.calls == [
        {
            "model": "qwen2.5",
            "prompt": None,
            "messages": [{"role": "user", "content": "ping"}],
        }
    ]


def test_run_script_gen_script_stores_state_and_writes_artifact(tmp_path):
    script = tmp_path / "demo.choom"
    script.write_text(
        'gen script id=plan text="toolcall tool name=echo msg=hi"\n',
        encoding="utf-8",
    )

    workdir = tmp_path / "run"
    outputs = run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))

    assert outputs == ["line 1: toolcall tool name=echo msg=hi"]
    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert state["plan"] == "toolcall tool name=echo msg=hi"
    assert (workdir / "artifacts" / "plan.choom").read_text(encoding="utf-8") == "toolcall tool name=echo msg=hi"


def test_run_script_summarizes_a1111_outputs_in_transcript_without_changing_state(tmp_path, monkeypatch):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=a1111_txt2img id=imgs\n", encoding="utf-8")

    def fake_run_adapter(name, params, artifacts_dir, dry_run, **kwargs):
        _ = name
        _ = params
        _ = artifacts_dir
        _ = dry_run
        _ = kwargs
        return '["a1111_txt2img_0001_01_seedx.png","nested/image_02.png"]'

    monkeypatch.setattr("choomlang.runner.run_adapter", fake_run_adapter)

    workdir = tmp_path / "run"
    run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))

    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert state["imgs"] == '["a1111_txt2img_0001_01_seedx.png","nested/image_02.png"]'

    record = json.loads((workdir / "transcript.jsonl").read_text(encoding="utf-8").strip())
    assert record["output"] == {
        "files": ["a1111_txt2img_0001_01_seedx.png", "nested/image_02.png"],
        "count": 2,
    }


def test_run_script_does_not_summarize_non_relative_a1111_output_paths(tmp_path, monkeypatch):
    script = tmp_path / "demo.choom"
    script.write_text("toolcall tool name=a1111_txt2img\n", encoding="utf-8")

    monkeypatch.setattr(
        "choomlang.runner.run_adapter",
        lambda *args, **kwargs: '["../bad.png"]',
    )

    workdir = tmp_path / "run"
    run_script(str(script), config=RunnerConfig(workdir=str(workdir), dry_run=False))

    record = json.loads((workdir / "transcript.jsonl").read_text(encoding="utf-8").strip())
    assert record["output"] == '["../bad.png"]'
