"""Tests for the model download retry/error-handling logic in
package_models.py, specifically the handling of HuggingFace's Xet storage
CAS-bridge 403 failures - a well-documented, recurring issue on
HuggingFace's own infrastructure (confirmed via many independent reports
of the identical failure spanning many months), not something specific
to this project. Unlike a genuine 404/401, this is reported as
intermittent, so it's worth retrying rather than failing immediately;
these tests confirm both that retry behavior and that the resulting
error message clearly explains what's actually going on.

Important: in real usage, the ORIGINAL request URL is always a normal
huggingface.co resolve URL - only the response's final .url (after
requests transparently follows the redirect) points at the
xethub/cas-bridge domain. These are genuinely different strings, and an
earlier version of this fix checked the wrong one (the original URL),
which meant it silently never triggered for real downloads. Every test
here deliberately keeps that distinction, using an ordinary resolve URL
as input and only setting the xethub/cas-bridge domain on the mocked
response's .url, so a regression of that exact bug would be caught.
"""
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from promptsmith.scripts.package_models import _stream_download


ORDINARY_RESOLVE_URL = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
REDIRECTED_XET_BRIDGE_URL = (
    "https://cas-bridge.xethub.hf.co/xet-bridge-us/abc123/def456"
    "?Expires=1783988717&Policy=xyz&Signature=abc"
)


def _make_403_after_redirect() -> requests.exceptions.HTTPError:
    """Simulates exactly what happens in production: request an ordinary
    resolve URL, get transparently redirected to the xethub/cas-bridge
    domain, and that final destination returns 403. response.url reflects
    the final, post-redirect location - not the original request URL."""
    resp = requests.Response()
    resp.status_code = 403
    resp.reason = "Forbidden"
    resp.url = REDIRECTED_XET_BRIDGE_URL
    return requests.exceptions.HTTPError(
        f"403 Client Error: Forbidden for url: {REDIRECTED_XET_BRIDGE_URL}",
        response=resp,
    )


def test_xet_bridge_403_is_retried(tmp_path, monkeypatch):
    """The core fix: a 403 whose final (redirected) URL contains
    'xethub'/'cas-bridge' must be retried, not failed immediately - this
    is the exact failure reported in production. The function is called
    with an ordinary resolve URL, exactly as it would be in real use."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)  # don't actually wait in tests

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _make_403_after_redirect()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"content-length": "4"}
        # A successful download must now return a valid GGUF (magic bytes),
        # otherwise the post-download header check correctly rejects it.
        mock_resp.iter_content = lambda chunk_size: [b"GGUF"]
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        dest = tmp_path / "model.gguf"
        _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=3)

    assert call_count["n"] == 3
    assert dest.exists()


def test_xet_bridge_403_gives_clear_error_after_exhausting_retries(tmp_path, monkeypatch):
    """When every retry also fails, the error message must clearly
    explain this is a known HuggingFace-side issue, not a PromptSmith
    bug - not just surface the raw 403."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    def always_403(url, **kwargs):
        raise _make_403_after_redirect()

    with patch("requests.get", side_effect=always_403):
        dest = tmp_path / "model.gguf"
        with pytest.raises(RuntimeError) as exc_info:
            _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=3)

    message = str(exc_info.value)
    assert "known" in message.lower() or "recurring" in message.lower()
    assert "huggingface" in message.lower() or "xet" in message.lower()
    assert not dest.exists()


def test_non_xet_403_fails_immediately_without_retrying(tmp_path, monkeypatch):
    """A 403 whose final URL is NOT on the xethub/cas-bridge domain - e.g.
    a genuinely gated or unauthorized model - must still fail fast on the
    first attempt, exactly as before this fix. Retrying that would just
    waste time for no reason, since it's not the intermittent-
    infrastructure failure mode this fix specifically targets."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    call_count = {"n": 0}

    def always_403_no_redirect(url, **kwargs):
        call_count["n"] += 1
        resp = requests.Response()
        resp.status_code = 403
        resp.reason = "Forbidden"
        resp.url = url  # no redirect happened - same domain throughout
        raise requests.exceptions.HTTPError(response=resp)

    with patch("requests.get", side_effect=always_403_no_redirect):
        dest = tmp_path / "model.gguf"
        with pytest.raises(RuntimeError):
            _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=3)

    assert call_count["n"] == 1  # no retries for a non-Xet failure


def test_404_still_fails_immediately_as_before(tmp_path, monkeypatch):
    """Sanity check against a regression: genuine 404s (wrong filename,
    moved repo) must still fail fast, unaffected by the new Xet-specific
    retry path."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    call_count = {"n": 0}

    def always_404(url, **kwargs):
        call_count["n"] += 1
        resp = requests.Response()
        resp.status_code = 404
        resp.url = url
        raise requests.exceptions.HTTPError(response=resp)

    with patch("requests.get", side_effect=always_404):
        dest = tmp_path / "model.gguf"
        with pytest.raises(RuntimeError):
            _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=3)

    assert call_count["n"] == 1


def test_interrupted_write_never_leaves_a_file_at_dest_path(tmp_path, monkeypatch):
    """Regression test for an independent review's finding: downloads
    previously wrote directly to dest_path. If the process was killed
    mid-write (SIGKILL, power loss, or anything else no Python except
    block can catch), a truncated file was left at dest_path, and future
    runs' `if dest_path.exists(): skip` treated that corrupt file as a
    complete, valid download forever.

    Simulates this by raising mid-stream from inside iter_content, which
    Python *can* catch (unlike a real SIGKILL) - close enough to prove the
    dest_path.exists() check can no longer be fooled by a partial write,
    since writes now only ever land at dest_path via an atomic rename
    after a verified-complete download."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    def interrupted_iter_content(chunk_size):
        yield b"partial-data-then-boom"
        raise ConnectionError("simulated connection drop mid-stream")

    def fake_get(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"content-length": "999999"}  # deliberately unmatched
        mock_resp.iter_content = interrupted_iter_content
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        dest = tmp_path / "model.gguf"
        with pytest.raises(RuntimeError):
            _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)

    assert not dest.exists(), "a partial write must never be visible at dest_path"
    assert not dest.with_name(dest.name + ".part").exists(), ".part must be cleaned up on failure"


def test_size_mismatch_is_detected_even_without_an_exception(tmp_path, monkeypatch):
    """A short read that completes without raising (some servers/proxies
    just close the connection cleanly mid-transfer rather than erroring)
    must still be caught by comparing against Content-Length, not silently
    accepted as a complete file."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    def fake_get(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"content-length": "100"}  # claims 100 bytes
        mock_resp.iter_content = lambda chunk_size: [b"only-ten"]  # delivers far fewer
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        dest = tmp_path / "model.gguf"
        with pytest.raises(RuntimeError):
            _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)

    assert not dest.exists()


def test_successful_download_lands_at_dest_path_with_no_leftover_part_file(tmp_path, monkeypatch):
    """Sanity check: the happy path still works exactly as before, and the
    temp .part file doesn't linger after a successful atomic rename."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    def fake_get(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"content-length": "4"}
        # Valid GGUF magic so the header check accepts the completed file.
        mock_resp.iter_content = lambda chunk_size: [b"GGUF"]
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        dest = tmp_path / "model.gguf"
        _stream_download("test-model", ORDINARY_RESOLVE_URL, dest, max_attempts=1)

    assert dest.exists()
    assert dest.read_bytes() == b"GGUF"
    assert not dest.with_name(dest.name + ".part").exists()
