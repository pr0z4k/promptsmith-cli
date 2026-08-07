"""Tests for GGUF model-file validation and download hardening."""

import logging

import pytest

from promptsmith.scripts.package_models import (
    GGUF_MAGIC,
    InvalidModelFileError,
    _stream_download,
    download_custom_model,
    is_valid_gguf,
)


def _write(path, data: bytes):
    path.write_bytes(data)
    return path


def test_is_valid_gguf_accepts_real_header(tmp_path):
    f = _write(tmp_path / "good.gguf", GGUF_MAGIC + b"\x00\x01\x02rest of file")
    assert is_valid_gguf(f) is True


def test_is_valid_gguf_rejects_html(tmp_path):
    f = _write(tmp_path / "bad.gguf", b"<!DOCTYPE html><html>404 Not Found</html>")
    assert is_valid_gguf(f) is False


def test_is_valid_gguf_rejects_empty(tmp_path):
    f = _write(tmp_path / "empty.gguf", b"")
    assert is_valid_gguf(f) is False


def test_is_valid_gguf_rejects_truncated_magic(tmp_path):
    # Fewer bytes than the magic itself.
    f = _write(tmp_path / "short.gguf", b"GG")
    assert is_valid_gguf(f) is False


def test_is_valid_gguf_missing_file(tmp_path):
    assert is_valid_gguf(tmp_path / "does-not-exist.gguf") is False


def test_existing_invalid_file_is_replaced(tmp_path, monkeypatch):
    """If a file already sits at the destination but isn't a valid GGUF,
    the skip path must NOT trust it - it should remove it and proceed to
    download (here, download is faked to write a valid file)."""
    dest = tmp_path / "model.gguf"
    _write(dest, b"not a model, some corrupt junk")

    # Fake the network: replace the whole streaming body with a writer that
    # drops a valid GGUF at the .part path, so we exercise the skip->re-
    # download decision without real HTTP.

    class FakeResp:
        headers = {"content-length": str(len(GGUF_MAGIC) + 4)}
        url = "https://example/model.gguf"

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield GGUF_MAGIC + b"\x00\x00\x00\x00"

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def get(url, stream=True, timeout=60, allow_redirects=True):
            return FakeResp()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)

    _stream_download("model", "https://example/model.gguf", dest)
    assert dest.exists()
    assert is_valid_gguf(dest)


def test_download_rejects_non_gguf_body(tmp_path, monkeypatch):
    """A URL that returns an HTML page (not a model) must fail with
    InvalidModelFileError and leave no file behind, without retrying."""
    dest = tmp_path / "out.gguf"
    body = b"<!DOCTYPE html><html>login required</html>"

    class FakeResp:
        headers = {"content-length": str(len(body))}
        url = "https://example/out.gguf"

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield body

    call_count = {"n": 0}

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def get(url, stream=True, timeout=60, allow_redirects=True):
            call_count["n"] += 1
            return FakeResp()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)

    with pytest.raises(InvalidModelFileError):
        _stream_download("out", "https://example/out.gguf", dest, max_attempts=3)

    # Must NOT have retried a deterministic content failure.
    assert call_count["n"] == 1
    # No garbage left at the destination or the .part path.
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_custom_download_rejects_plain_http(tmp_path, monkeypatch):
    """Custom model downloads are HTTPS-only: a plain-HTTP URL must be
    rejected outright, before any network call is attempted."""
    import promptsmith.scripts.package_models as pm

    monkeypatch.setattr(pm, "MODEL_DIR", tmp_path)

    with pytest.raises(ValueError, match="HTTPS"):
        download_custom_model("http://example/thing.gguf")

    # No partial or final file should have been created.
    assert list(tmp_path.iterdir()) == []


def test_custom_download_https_succeeds(tmp_path, monkeypatch, caplog):
    """A well-formed HTTPS custom download completes without error."""
    body = GGUF_MAGIC + b"\x00\x00\x00\x00"

    class FakeResp:
        headers = {"content-length": str(len(body))}
        url = "https://example/thing.gguf"

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield body

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def get(url, stream=True, timeout=60, allow_redirects=True):
            return FakeResp()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    import promptsmith.scripts.package_models as pm

    monkeypatch.setattr(pm, "MODEL_DIR", tmp_path)

    with caplog.at_level(logging.WARNING):
        path = download_custom_model("https://example/thing.gguf")

    assert path.exists()
    assert is_valid_gguf(path)
