"""Regression coverage for user-reported v1 release-candidate defects."""

from __future__ import annotations

from pathlib import Path

from promptsmith.cli.launcher import PromptSmithApp
from promptsmith.scripts.model_catalog import MODEL_CATALOG


ROOT = Path(__file__).resolve().parents[2]


def test_phi4_catalog_uses_hub_identity_and_checksum() -> None:
    config = MODEL_CATALOG["phi4-mini"]
    assert config["repo_id"] == "bartowski/microsoft_Phi-4-mini-instruct-GGUF"
    assert config["file"] == "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    assert len(config["sha256"]) == 64
    int(config["sha256"], 16)
    assert "url" not in config


def test_standard_install_includes_local_slm_runtime() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = pyproject.split("[project.urls]", 1)[0]
    assert '"llama-cpp-python==0.3.34"' in dependencies
    assert '"huggingface-hub==0.34.3"' in dependencies
    assert 'promptsmith = "promptsmith.cli.launcher:main"' in pyproject
    assert 'promptsmith-cli = "promptsmith.cli.launcher:main"' in pyproject


def test_analyze_no_longer_steals_ctrl_a() -> None:
    bindings = {(binding.key, binding.action) for binding in PromptSmithApp.BINDINGS}
    assert ("ctrl+enter", "analyze") in bindings
    assert ("ctrl+a", "analyze") not in bindings
