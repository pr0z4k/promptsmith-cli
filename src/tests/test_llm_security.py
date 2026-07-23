"""Security and recovery tests for the local LLM backends."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from promptsmith.core.backends.hybrid_backend import HybridBackend
from promptsmith.core.backends.llm_backend import LLMBasedBackend


def _model_file(tmp_path: Path, name: str = "model.gguf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"GGUF" + b"\x00" * 100_000_000)
    return path


def test_symlinked_model_is_rejected(tmp_path):
    target = _model_file(tmp_path, "target.gguf")
    link = tmp_path / "linked.gguf"
    link.symlink_to(target)

    backend = LLMBasedBackend(model_path=link)
    assert backend._validate_model_path(link) is False


def test_memory_error_detection_handles_native_messages():
    assert LLMBasedBackend._is_memory_error(MemoryError())
    assert LLMBasedBackend._is_memory_error(RuntimeError("failed to allocate buffer"))
    assert not LLMBasedBackend._is_memory_error(RuntimeError("invalid tensor shape"))


def test_refine_oom_unloads_model_and_redacts_prompt(tmp_path, caplog):
    secret = "token=super-secret-value"
    backend = LLMBasedBackend(model_path=_model_file(tmp_path))
    model = MagicMock()
    model.create_chat_completion.side_effect = RuntimeError("CUDA error out of memory")
    backend.llm = model
    backend._model_loaded = True

    with caplog.at_level(logging.DEBUG):
        result = backend.refine(secret, {"role": "Engineer"})

    assert result is None
    assert backend.llm is None
    assert backend._model_loaded is False
    assert "out of memory" in backend.last_error.lower()
    assert secret not in caplog.text
    assert "super-secret-value" not in caplog.text


def test_success_log_contains_only_result_length(tmp_path, caplog):
    secret_output = "refined-private-content"
    backend = LLMBasedBackend(model_path=_model_file(tmp_path))
    backend.llm = MagicMock()
    backend.llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": secret_output}}]
    }
    backend._model_loaded = True

    with caplog.at_level(logging.DEBUG):
        assert backend.refine("private-input", {"role": "Engineer"}) == secret_output

    assert secret_output not in caplog.text
    assert "private-input" not in caplog.text
    assert f"characters={len(secret_output)}" in caplog.text


def test_unload_uses_close_and_is_idempotent(tmp_path):
    backend = LLMBasedBackend(model_path=_model_file(tmp_path))
    model = MagicMock()
    backend.llm = model
    backend._model_loaded = True

    backend.unload()
    backend.unload()

    model.close.assert_called_once_with()
    assert backend.llm is None
    assert backend._model_loaded is False


def test_hybrid_exception_details_are_not_exposed(tmp_path, caplog):
    secret = "native failure leaked-secret"
    backend = HybridBackend(model_path=_model_file(tmp_path))

    with patch.object(LLMBasedBackend, "refine", side_effect=RuntimeError(secret)):
        with caplog.at_level(logging.DEBUG):
            result = backend.refine("build a card", {"role": "Engineer"})

    assert result is not None
    assert secret not in backend.last_error
    assert secret not in caplog.text
