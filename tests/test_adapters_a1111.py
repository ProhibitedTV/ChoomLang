import base64
import json
from pathlib import Path

import pytest

from choomlang.adapters import resolve_artifact_path, run_adapter
from choomlang.errors import RunError


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _tiny_png_bytes_1() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3X8AAAAASUVORK5CYII=",
        validate=True,
    )


def _tiny_png_bytes_2() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/lXvVsQAAAABJRU5ErkJggg==",
        validate=True,
    )


def test_a1111_txt2img_maps_params_and_writes_deterministic_files(tmp_path, monkeypatch):
    calls: list[dict[str, object]] = []
    png_1 = _tiny_png_bytes_1()
    png_2 = _tiny_png_bytes_2()

    def fake_urlopen(req, timeout=None):
        calls.append(
            {
                "url": req.full_url,
                "timeout": timeout,
                "body": json.loads(req.data.decode("utf-8")),
                "content_type": req.get_header("Content-type"),
            }
        )
        return _FakeResponse(
            {
                "images": [
                    base64.b64encode(png_1).decode("ascii"),
                    base64.b64encode(png_2).decode("ascii"),
                ]
            }
        )

    monkeypatch.setattr("choomlang.adapters.request.urlopen", fake_urlopen)

    artifacts_dir = tmp_path / "artifacts"
    out = run_adapter(
        "a1111_txt2img",
        {
            "prompt": "cat",
            "negative": "bad",
            "cfg": 7,
            "n": "2",
            "sampler": "Euler a",
            "width": "512",
            "height": 768,
            "steps": "20",
            "seed": "123",
            "step": "4",
            "base_url": "http://localhost:7861/",
        },
        artifacts_dir,
        False,
        timeout=5.0,
    )

    assert json.loads(out) == [
        "a1111_txt2img_0004_01_seed123.png",
        "a1111_txt2img_0004_02_seed123.png",
    ]
    assert (artifacts_dir / "a1111_txt2img_0004_01_seed123.png").read_bytes() == png_1
    assert (artifacts_dir / "a1111_txt2img_0004_02_seed123.png").read_bytes() == png_2

    assert calls == [
        {
            "url": "http://localhost:7861/sdapi/v1/txt2img",
            "timeout": 5.0,
            "body": {
                "prompt": "cat",
                "negative_prompt": "bad",
                "cfg_scale": 7,
                "batch_size": 2,
                "sampler_name": "Euler a",
                "width": 512,
                "height": 768,
                "steps": 20,
                "seed": 123,
            },
            "content_type": "application/json",
        }
    ]


def test_a1111_txt2img_uses_context_base_url_and_seedx_when_seed_missing(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        _ = timeout
        assert req.full_url == "http://example:9000/sdapi/v1/txt2img"
        return _FakeResponse({"images": [base64.b64encode(b"img").decode("ascii")]})

    monkeypatch.setattr("choomlang.adapters.request.urlopen", fake_urlopen)

    artifacts_dir = tmp_path / "artifacts"
    out = run_adapter(
        "a1111_txt2img",
        {
            "context": {"base_url": "http://example:9000"},
            "step": 2,
        },
        artifacts_dir,
        False,
    )

    assert json.loads(out) == ["a1111_txt2img_0002_01_seedx.png"]
    assert (artifacts_dir / "a1111_txt2img_0002_01_seedx.png").read_bytes() == b"img"




def test_a1111_txt2img_uses_invocation_context_for_step_and_url(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        _ = timeout
        assert req.full_url == "http://context:7862/sdapi/v1/txt2img"
        return _FakeResponse({"images": [base64.b64encode(b"img").decode("ascii")]})

    monkeypatch.setattr("choomlang.adapters.request.urlopen", fake_urlopen)

    artifacts_dir = tmp_path / "artifacts"
    out = run_adapter(
        "a1111_txt2img",
        {"prompt": "cat"},
        artifacts_dir,
        False,
        context={"step": 9, "a1111_url": "http://context:7862"},
    )

    assert json.loads(out) == ["a1111_txt2img_0009_01_seedx.png"]
    assert (artifacts_dir / "a1111_txt2img_0009_01_seedx.png").read_bytes() == b"img"

def test_a1111_txt2img_rejects_invalid_batch_size(tmp_path):
    with pytest.raises(RunError, match="param 'n' must be an integer >= 1"):
        run_adapter("a1111_txt2img", {"n": 0}, tmp_path / "artifacts", False)


def test_a1111_txt2img_rejects_non_image_response(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        _ = req
        _ = timeout
        return _FakeResponse({"images": [1]})

    monkeypatch.setattr("choomlang.adapters.request.urlopen", fake_urlopen)

    with pytest.raises(RunError, match="must include an 'images' list"):
        run_adapter("a1111_txt2img", {}, tmp_path / "artifacts", False)


def test_a1111_txt2img_dry_run_returns_empty_list_without_request(tmp_path, monkeypatch):
    def fail_urlopen(req, timeout=None):  # pragma: no cover - should not execute
        raise AssertionError("urlopen should not be called in dry-run")

    monkeypatch.setattr("choomlang.adapters.request.urlopen", fail_urlopen)

    out = run_adapter("a1111_txt2img", {"prompt": "cat"}, tmp_path / "artifacts", True)
    assert out == "[]"


def test_resolve_artifact_path_rejects_traversal_and_absolute_paths(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    with pytest.raises(RunError, match="path traversal"):
        resolve_artifact_path(artifacts_dir, "../escape.png")

    with pytest.raises(RunError, match="absolute paths are not allowed"):
        resolve_artifact_path(artifacts_dir, "/tmp/escape.png")
