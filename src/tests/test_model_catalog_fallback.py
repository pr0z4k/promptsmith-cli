"""Regression tests for the resilient built-in model catalog."""

from pathlib import Path
from typing import Any

import pytest

from promptsmith.scripts import model_catalog, package_models


def test_phi_catalog_pins_primary_source_and_keeps_checksum() -> None:
    cfg = model_catalog.MODEL_CATALOG["phi4-mini"]

    assert cfg["sources"][0].endswith(
        "/resolve/915429c/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    )
    assert cfg["sources"][1].endswith(
        "/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    )
    assert len(cfg["sha256"]) == 64


def test_preset_download_uses_next_source_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts: list[str] = []

    monkeypatch.setattr(package_models, "_safe_filename", lambda value: value)
    monkeypatch.setattr(package_models, "_confined_model_path", lambda value: tmp_path / value)

    def fake_stream_download(
        label: str,
        url: str,
        destination: Path,
        progress_callback: Any = None,
        expected_sha256: str | None = None,
    ) -> None:
        attempts.append(url)
        assert label == "phi4-mini"
        assert destination == tmp_path / "model.gguf"
        assert expected_sha256 == "a" * 64
        if len(attempts) == 1:
            raise RuntimeError("primary unavailable")

    monkeypatch.setattr(package_models, "_stream_download", fake_stream_download)

    model_catalog._download_model_from_catalog(
        "phi4-mini",
        {
            "file": "model.gguf",
            "sources": ["https://example.com/pinned.gguf", "https://example.com/main.gguf"],
            "sha256": "a" * 64,
        },
    )

    assert attempts == [
        "https://example.com/pinned.gguf",
        "https://example.com/main.gguf",
    ]


def test_preset_download_reports_all_failed_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(package_models, "_safe_filename", lambda value: value)
    monkeypatch.setattr(package_models, "_confined_model_path", lambda value: tmp_path / value)

    def fail_every_source(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(package_models, "_stream_download", fail_every_source)

    with pytest.raises(RuntimeError, match="all 2 configured sources") as exc_info:
        model_catalog._download_model_from_catalog(
            "phi4-mini",
            {
                "file": "model.gguf",
                "sources": ["https://example.com/one.gguf", "https://example.com/two.gguf"],
                "sha256": "a" * 64,
            },
        )

    assert "source 1" in str(exc_info.value)
    assert "source 2" in str(exc_info.value)


def test_security_failure_does_not_fall_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0
    monkeypatch.setattr(package_models, "_safe_filename", lambda value: value)
    monkeypatch.setattr(package_models, "_confined_model_path", lambda value: tmp_path / value)

    def reject_source(*args: Any, **kwargs: Any) -> None:
        nonlocal attempts
        attempts += 1
        raise package_models.DownloadSecurityError("unsafe redirect")

    monkeypatch.setattr(package_models, "_stream_download", reject_source)

    with pytest.raises(package_models.DownloadSecurityError, match="unsafe redirect"):
        model_catalog._download_model_from_catalog(
            "phi4-mini",
            {
                "file": "model.gguf",
                "sources": ["https://example.com/one.gguf", "https://example.com/two.gguf"],
            },
        )

    assert attempts == 1
