"""Tests for LLMBasedBackend, focused on the chat_format validation bug:
a guessed chat_format name (e.g. 'phi3') may not actually be registered in
the installed llama-cpp-python version. That error was previously only
discovered lazily, at inference time inside create_chat_completion() - not
at Llama() construction time - so a naive try/except around the constructor
call never caught it. These tests guard the fix: validate the format name
against the real registry *before* ever using it.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from promptsmith.core.backends.llm_backend import LLMBasedBackend


@pytest.fixture
def fake_registry(monkeypatch):
    """Simulate llama_cpp.llama_chat_format's real registry behavior,
    including a version where 'phi3' is genuinely not registered - matching
    what was observed in production."""
    valid_formats = [
        "llama-2", "llama-3", "alpaca", "qwen", "vicuna", "oasst_llama",
        "baichuan-2", "baichuan", "zephyr", "chatml", "mistral-instruct",
    ]

    def fake_get_handler(name):
        if name not in valid_formats:
            raise Exception(f"Invalid chat handler: {name} (valid formats: {valid_formats})")
        return MagicMock()

    fake_module = MagicMock()
    fake_module.get_chat_completion_handler = fake_get_handler
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_chat_format", fake_module)
    return valid_formats


def test_validate_chat_format_rejects_unregistered_name(fake_registry):
    """'phi3' isn't registered in this simulated version (matching the real
    bug report) - validation must catch this and fall back to None rather
    than let the invalid name reach Llama()."""
    result = LLMBasedBackend._validate_chat_format("phi3")
    assert result is None


def test_validate_chat_format_accepts_registered_name(fake_registry):
    result = LLMBasedBackend._validate_chat_format("zephyr")
    assert result == "zephyr"


def test_validate_chat_format_passes_through_none(fake_registry):
    result = LLMBasedBackend._validate_chat_format(None)
    assert result is None


def test_detect_chat_format_by_filename():
    cases = [
        ("microsoft_Phi-4-mini-instruct-Q4_K_M.gguf", "phi3"),
        ("Phi-3-mini-4k-instruct-q4.gguf", "phi3"),
        ("tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf", "zephyr"),
        ("some-custom-model.gguf", None),
    ]
    for filename, expected in cases:
        backend = LLMBasedBackend(model_path=Path(f"/models/{filename}"))
        assert backend._detect_chat_format() == expected


def test_load_model_never_passes_unregistered_format_to_llama(fake_registry, monkeypatch, tmp_path):
    """End-to-end: even though _detect_chat_format() guesses 'phi3' for a
    Phi-4 model, and 'phi3' isn't actually registered in this environment,
    Llama() must never be constructed with chat_format='phi3'. This is the
    exact bug that previously reached production as a visible warning and
    silent fallback to the rule-based backend."""
    model_path = tmp_path / "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    model_path.write_bytes(b"GGUF" + b"\x00" * 200_000_000)

    captured_kwargs = {}

    def fake_llama_init(self, **kwargs):
        captured_kwargs.update(kwargs)

    fake_llama_cpp = MagicMock()
    fake_llama_cpp.Llama = type("FakeLlama", (), {"__init__": fake_llama_init})
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)

    backend = LLMBasedBackend(model_path=model_path)
    backend._load_model()

    assert captured_kwargs.get("chat_format") != "phi3"
    assert captured_kwargs.get("chat_format") is None


def test_is_thinking_model_by_filename():
    cases = [
        ("Qwen_Qwen3-8B-Q4_K_M.gguf", True),
        ("qwen3-8b-instruct.Q4_K_M.gguf", True),
        ("QwQ-32B-Preview-Q4_K_M.gguf", True),
        ("DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf", True),
        ("microsoft_Phi-4-mini-instruct-Q4_K_M.gguf", False),
        ("some-custom-model.gguf", False),
    ]
    for filename, expected in cases:
        backend = LLMBasedBackend(model_path=Path(f"/models/{filename}"))
        assert backend._is_thinking_model() is expected, filename


def test_strip_think_blocks_removes_closed_block():
    text = "<think>reasoning about the answer</think>Here is the actual rewritten request."
    assert LLMBasedBackend._strip_think_blocks(text) == "Here is the actual rewritten request."


def test_strip_think_blocks_treats_unclosed_block_as_empty():
    """Regression test for a real production scenario: Qwen3's 512-token
    response budget was entirely consumed by mid-sentence reasoning that
    never reached a closing </think> tag or an actual answer. The response
    was long (not caught by length-based degenerate checks) but contained
    zero usable content."""
    truncated = (
        "<think>\nOkay, let's tackle this request. The user wants a reusable "
        "React component for a product card. First, I need to make sure I "
        "understand all the requirements... Then, when the button is clicked, it"
    )
    assert LLMBasedBackend._strip_think_blocks(truncated) == ""


def test_strip_think_blocks_passthrough_when_no_think_tags():
    text = "Create a login form with validation and a submit button."
    assert LLMBasedBackend._strip_think_blocks(text) == text


def test_refine_falls_back_to_none_on_truncated_think_block(monkeypatch, tmp_path):
    """End-to-end: a Qwen-style model whose entire response is an unclosed
    <think> block must make refine() return None (triggering HybridBackend's
    fallback to the rule-based result), not the raw unfinished reasoning."""
    model_path = tmp_path / "Qwen_Qwen3-8B-Q4_K_M.gguf"
    model_path.write_bytes(b"GGUF" + b"\x00" * 200_000_000)

    truncated_response = {
        "choices": [{
            "message": {
                "content": (
                    "<think>\nOkay, let's tackle this request. The user wants "
                    "a reusable React component for a product card..."
                )
            }
        }]
    }

    backend = LLMBasedBackend(model_path=model_path)
    backend.llm = MagicMock()
    backend.llm.create_chat_completion.return_value = truncated_response
    backend._model_loaded = True

    result = backend.refine("a product card", {"role": "Engineer"}, polish_mode=True)

    assert result is None
    assert "think" in backend.last_error.lower()


def test_refine_appends_no_think_for_qwen3_models(tmp_path):
    """Qwen3's documented control switch to skip its reasoning phase -
    avoids wasting the fixed max_tokens budget on unwanted reasoning in
    the common case (the <think>-stripping above is the safety net for
    when this doesn't apply, e.g. custom-downloaded reasoning models)."""
    model_path = tmp_path / "Qwen_Qwen3-8B-Q4_K_M.gguf"
    model_path.write_bytes(b"GGUF" + b"\x00" * 200_000_000)

    backend = LLMBasedBackend(model_path=model_path)
    backend.llm = MagicMock()
    backend.llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "Create a login form."}}]
    }
    backend._model_loaded = True

    backend.refine("a login form", {"role": "Engineer"}, polish_mode=True)

    call_kwargs = backend.llm.create_chat_completion.call_args.kwargs
    user_message = call_kwargs["messages"][1]["content"]
    assert user_message.endswith("/no_think")


def test_refine_does_not_append_no_think_for_non_thinking_models(tmp_path):
    model_path = tmp_path / "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    model_path.write_bytes(b"GGUF" + b"\x00" * 200_000_000)

    backend = LLMBasedBackend(model_path=model_path)
    backend.llm = MagicMock()
    backend.llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "Create a login form."}}]
    }
    backend._model_loaded = True

    backend.refine("a login form", {"role": "Engineer"}, polish_mode=True)

    call_kwargs = backend.llm.create_chat_completion.call_args.kwargs
    user_message = call_kwargs["messages"][1]["content"]
    assert "/no_think" not in user_message
