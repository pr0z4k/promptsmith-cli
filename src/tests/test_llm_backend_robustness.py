"""Security and recovery tests for the local LLM backend."""

import logging
import sys
from unittest.mock import MagicMock

from promptsmith.core.backends.llm_backend import LLMBasedBackend


def test_model_load_oom_fails_cleanly(monkeypatch, tmp_path):
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"GGUF")

    fake_llama_cpp = MagicMock()
    fake_llama_cpp.Llama.side_effect = MemoryError("secret allocator details")
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)

    backend = LLMBasedBackend(model_path=model_path)
    monkeypatch.setattr(backend, "_validate_model_path", lambda _path: True)

    assert backend._load_model() is False
    assert backend.llm is None
    assert backend._model_loaded is False
    assert backend.last_error is not None
    assert "memory" in backend.last_error.lower()
    assert "secret allocator details" not in backend.last_error


def test_refine_oom_unloads_model(tmp_path):
    backend = LLMBasedBackend(model_path=tmp_path / "model.gguf")
    model = MagicMock()
    model.create_chat_completion.side_effect = RuntimeError("CUDA error out of memory")
    backend.llm = model
    backend._model_loaded = True

    result = backend.refine("private prompt", {"role": "Engineer"})

    assert result is None
    assert backend.llm is None
    assert backend._model_loaded is False
    assert backend.last_error is not None
    assert "memory" in backend.last_error.lower()
    model.close.assert_called_once_with()


def test_success_logs_metadata_not_prompt_content(caplog, tmp_path):
    backend = LLMBasedBackend(model_path=tmp_path / "model.gguf")
    model = MagicMock()
    model.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "REFINED_SECRET_VALUE"}}]
    }
    backend.llm = model
    backend._model_loaded = True

    with caplog.at_level(logging.DEBUG):
        assert backend.refine("PROMPT_SECRET_VALUE", {"role": "Engineer"})

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "PROMPT_SECRET_VALUE" not in log_text
    assert "REFINED_SECRET_VALUE" not in log_text
    assert "characters=" in log_text


def test_unload_is_idempotent_and_closes_native_model(tmp_path):
    backend = LLMBasedBackend(model_path=tmp_path / "model.gguf")
    model = MagicMock()
    backend.llm = model
    backend._model_loaded = True

    backend.unload()
    backend.unload()

    model.close.assert_called_once_with()
    assert backend.llm is None
    assert backend._model_loaded is False
