import pytest
from unittest.mock import patch
from promptsmith.core.backends.hybrid_backend import HybridBackend
from promptsmith.core.backends.llm_backend import LLMBasedBackend


@pytest.fixture
def profile():
    return {
        "role": "React Developer",
        "domain": ["React", "TypeScript"],
        "tone": "Technical",
        "format": "Markdown",
        "constraints": ["Include tests.", "Handle errors gracefully."],
    }


def test_hybrid_polishes_rule_based_result(profile):
    backend = HybridBackend()
    polished_text = (
        "Build a React product card with tests and graceful error handling, "
        "written by a technical React/TypeScript engineer, formatted as Markdown."
    )
    with patch.object(LLMBasedBackend, "refine", return_value=polished_text) as mock_refine:
        result = backend.refine("a product card", profile)
    assert result == polished_text
    args, kwargs = mock_refine.call_args
    assert kwargs.get("polish_mode") is True or (len(args) >= 3 and args[2] is True)
    passed_prompt = args[0] if args else kwargs.get("prompt")
    assert "Act as if I am React Developer" in passed_prompt
    assert "Include tests." in passed_prompt


def test_hybrid_falls_back_when_llm_returns_none(profile):
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", return_value=None):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert "Include tests." in result
    assert backend.last_error is not None


def test_hybrid_falls_back_on_llm_exception(profile):
    backend = HybridBackend()
    with patch.object(
        LLMBasedBackend,
        "refine",
        side_effect=RuntimeError("model crashed with private details"),
    ):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert backend.last_error is not None
    assert "private details" not in backend.last_error


def test_hybrid_falls_back_on_degenerate_output(profile):
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", return_value="ok"):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert backend.last_error is not None


def test_hybrid_accepts_reasonable_length_polish(profile):
    from promptsmith.core.models import _apply_rules

    backend = HybridBackend()
    rule_based = _apply_rules("a product card", profile)
    target_len = int(len(rule_based) * 0.7)
    reasonable_polish = (
        "A React product card built by a technical engineer, "
        "with tests and graceful error handling throughout. " * 3
    )[:target_len]
    with patch.object(LLMBasedBackend, "refine", return_value=reasonable_polish):
        result = backend.refine("a product card", profile)
    assert result == reasonable_polish


def test_hybrid_falls_back_when_llm_returns_none_from_truncated_thinking(profile):
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", return_value=None):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "React Developer" in result
    assert "React" in result and "TypeScript" in result
    assert "Include tests." in result
