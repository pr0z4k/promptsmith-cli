"""Regression coverage for user-reported v1 release-candidate defects."""

from __future__ import annotations

from pathlib import Path

from promptsmith.cli.launcher import PromptSmithApp
from promptsmith.core.backends.llm_backend import LLMBasedBackend
from promptsmith.core.runtime_model_fixes import configure_runtime_model_behavior
from promptsmith.scripts.model_catalog import MODEL_CATALOG

ROOT = Path(__file__).resolve().parents[2]


def test_phi4_catalog_uses_correct_public_url_and_checksum() -> None:
    config = MODEL_CATALOG["phi4-mini"]
    assert config["sources"], "expected at least one source URL"
    for source in config["sources"]:
        assert source.startswith(
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF/"
        )
    assert config["file"] == "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    assert len(config["sha256"]) == 64
    int(config["sha256"], 16)
    assert "repo_id" not in config
    assert "url" not in config  # superseded by the multi-source "sources" list


def test_standard_install_includes_local_slm_runtime() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = pyproject.split("[project.urls]", 1)[0]
    # llama-cpp-python must be a required dependency (not tucked away in
    # [project.optional-dependencies]) so a standard install always
    # includes local SLM support. The exact version is pinned separately
    # in requirements/constraints-release.txt for reproducible release
    # artifacts; this check only cares that it's required, not optional.
    assert '"llama-cpp-python' in dependencies
    assert 'promptsmith = "promptsmith.cli.launcher:main"' in pyproject
    assert 'promptsmith-cli = "promptsmith.cli.launcher:main"' in pyproject


def test_editor_shortcuts_do_not_steal_ctrl_a() -> None:
    bindings = {(binding.key, binding.action) for binding in PromptSmithApp.BINDINGS}
    assert ("ctrl+enter", "analyze") in bindings
    assert ("ctrl+shift+a", "select_prompt_all") in bindings
    assert ("ctrl+a", "analyze") not in bindings


def test_unclosed_think_marker_does_not_delete_small_model_answer() -> None:
    configure_runtime_model_behavior()
    result = LLMBasedBackend._strip_think_blocks("<think>Rewrite this request clearly")
    assert result == "Rewrite this request clearly"
