"""Security and robustness tests for model downloads."""

import hashlib
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from promptsmith.scripts.package_models import (
    CONNECT_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    DownloadSecurityError,
    InvalidModelFileError,
    _safe_filename,
    _stream_download,
    _validate_https_url,
    download_custom_model,
    filename_from_url,
)

ORDINARY_RESOLVE_URL = (
    "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/"
    "resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
)
REDIRECTED_XET_BRIDGE_URL = (
    "https://cas-bridge.xethub.hf.co/xet-bridge-us/abc123/def456"
    "?Expires=1783988717&Policy=xyz&Signature=abc"
)


def _response(chunks=(b"GGUF",), *, status=200, url=ORDINARY_RESOLVE_URL, total=None):
    response = MagicMock()
    response.url = url
    response.status_code = status
    response.headers = {
        "content-length": str(sum(len(chunk) for chunk in chunks) if total is None else total)
    }
    response.iter_content = MagicMock(side_effect=lambda chunk_size: iter(chunks))
    if status >= 400:
        error = requests.HTTPError(response=response)
        response.raise_for_status.side_effect = error
    else:
        response.raise_for_status.return_value = None
    return response


def _xet_403():
    response = _response(status=403, url=REDIRECTED_XET_BRIDGE_URL)
    return requests.HTTPError(response=response)


def test_https_url_validation_rejects_insecure_or_credentialed_sources():
    assert _validate_https_url(ORDINARY_RESOLVE_URL) == ORDINARY_RESOLVE_URL
    with pytest.raises(ValueError, match="HTTPS"):
        _validate_https_url("http://example.com/model.gguf")
    with pytest.raises(ValueError, match="credentials"):
        _validate_https_url("https://user:secret@example.com/model.gguf")
    with pytest.raises(ValueError, match="fragment"):
        _validate_https_url("https://example.com/model.gguf#ignored")


@pytest.mark.parametrize(
    "name",
    ["../escape.gguf", "folder/model.gguf", r"folder\\model.gguf", ".gguf", "bad name.gguf"],
)
def test_custom_filename_rejects_path_traversal_and_unsafe_names(name):
    with pytest.raises(ValueError):
        _safe_filename(name)


def test_filename_from_url_decodes_and_sanitizes_basename():
    assert filename_from_url("https://example.com/models/My%20Model.gguf?download=1") == "My_Model.gguf"
    assert filename_from_url("https://example.com/download") == "download.gguf"


def test_request_uses_split_timeouts_and_redirect_validation(tmp_path):
    response = _response(url="https://cdn.example.com/model.gguf")
    with patch("requests.get", return_value=response) as mocked_get:
        _stream_download("model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=1)
    mocked_get.assert_called_once_with(
        ORDINARY_RESOLVE_URL,
        stream=True,
        timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        allow_redirects=True,
    )


def test_https_to_http_redirect_is_rejected_before_body_is_written(tmp_path):
    response = _response(url="http://cdn.example.com/model.gguf")
    dest = tmp_path / "model.gguf"
    with patch("requests.get", return_value=response):
        with pytest.raises(ValueError, match="HTTPS"):
            _stream_download("model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)
    assert not dest.exists()
    response.iter_content.assert_not_called()


def test_xet_bridge_403_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _xet_403()
        return _response()

    with patch("requests.get", side_effect=fake_get):
        _stream_download("test-model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=3)
    assert calls["count"] == 3


def test_xet_bridge_403_has_clear_final_error(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    with patch("requests.get", side_effect=_xet_403()):
        with pytest.raises(RuntimeError, match="Xet storage"):
            _stream_download("test-model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=3)


def test_non_retryable_404_fails_immediately(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        response = _response(status=404)
        raise requests.HTTPError(response=response)

    with patch("requests.get", side_effect=fake_get):
        with pytest.raises(RuntimeError, match="HTTP 404"):
            _stream_download("model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=3)
    assert calls["count"] == 1


def test_retryable_503_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            response = _response(status=503)
            raise requests.HTTPError(response=response)
        return _response()

    with patch("requests.get", side_effect=fake_get):
        _stream_download("model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=2)
    assert calls["count"] == 2


def test_interrupted_write_never_reaches_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    def chunks(chunk_size):
        yield b"GGUFpartial"
        raise requests.ConnectionError("simulated drop")

    response = _response()
    response.iter_content = MagicMock(side_effect=chunks)
    dest = tmp_path / "model.gguf"
    with patch("requests.get", return_value=response):
        with pytest.raises(RuntimeError):
            _stream_download("model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)
    assert not dest.exists()
    assert not dest.with_name("model.gguf.part").exists()


def test_stale_partial_file_is_removed_before_download(tmp_path):
    dest = tmp_path / "model.gguf"
    part = tmp_path / "model.gguf.part"
    part.write_bytes(b"stale")
    with patch("requests.get", return_value=_response()):
        _stream_download("model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)
    assert dest.read_bytes() == b"GGUF"
    assert not part.exists()


def test_symlinked_destination_is_rejected(tmp_path):
    target = tmp_path / "target.gguf"
    target.write_bytes(b"GGUF")
    dest = tmp_path / "model.gguf"
    try:
        dest.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(DownloadSecurityError):
        _stream_download("model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)


def test_size_mismatch_is_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    response = _response(chunks=(b"GGUF",), total=100)
    with patch("requests.get", return_value=response):
        with pytest.raises(RuntimeError, match="does not match"):
            _stream_download("model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", max_attempts=1)


def test_checksum_success_and_mismatch(tmp_path):
    checksum = hashlib.sha256(b"GGUF").hexdigest()
    good = tmp_path / "good.gguf"
    with patch("requests.get", return_value=_response()):
        _stream_download(
            "model", ORDINARY_RESOLVE_URL, good, max_attempts=1, expected_sha256=checksum
        )
    assert good.exists()

    bad = tmp_path / "bad.gguf"
    with patch("requests.get", return_value=_response()):
        with pytest.raises(InvalidModelFileError, match="SHA-256 mismatch"):
            _stream_download(
                "model", ORDINARY_RESOLVE_URL, bad, max_attempts=1, expected_sha256="0" * 64
            )
    assert not bad.exists()


def test_invalid_checksum_format_fails_before_network(tmp_path):
    with patch("requests.get") as mocked_get:
        with pytest.raises(ValueError, match="64 hexadecimal"):
            _stream_download(
                "model", ORDINARY_RESOLVE_URL, tmp_path / "model.gguf", expected_sha256="bad"
            )
    mocked_get.assert_not_called()


def test_custom_download_requires_https_before_resolving_destination():
    with pytest.raises(ValueError, match="HTTPS"):
        download_custom_model("http://example.com/model.gguf")
