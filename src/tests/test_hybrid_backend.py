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
    """When the LLM succeeds, hybrid should return its polished text."""
    backend = HybridBackend()
    polished_text = (
        "Build a React product card with tests and graceful error handling, "
        "written by a technical React/TypeScript engineer, formatted as Markdown."
    )
    with patch.object(LLMBasedBackend, "refine", return_value=polished_text) as mock_refine:
        result = backend.refine("a product card", profile)
    assert result == polished_text
    # Confirm polish_mode was requested, and the LLM was given the
    # rule-expanded text (not the bare raw prompt) to work with.
    args, kwargs = mock_refine.call_args
    assert kwargs.get("polish_mode") is True or (len(args) >= 3 and args[2] is True)
    passed_prompt = args[0] if args else kwargs.get("prompt")
    assert "Act as if I am React Developer" in passed_prompt
    assert "Include tests." in passed_prompt


def test_hybrid_falls_back_when_llm_returns_none(profile):
    """If the LLM backend can't produce anything (e.g. no model loaded),
    hybrid should fall back to the pure rule-based result, not fail."""
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", return_value=None):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert "Include tests." in result
    assert backend.last_error is not None


def test_hybrid_falls_back_on_llm_exception(profile):
    """If the LLM backend raises, hybrid should still return a usable result."""
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", side_effect=RuntimeError("model crashed")):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert backend.last_error is not None
    assert "model crashed" in backend.last_error


def test_hybrid_falls_back_on_degenerate_output(profile):
    """If the LLM returns something drastically shorter than what it was
    given (a sign of truncation/failure), hybrid should distrust it and
    fall back to the rule-based text rather than return broken output."""
    backend = HybridBackend()
    with patch.object(LLMBasedBackend, "refine", return_value="ok"):
        result = backend.refine("a product card", profile)
    assert result is not None
    assert "Act as if I am React Developer" in result
    assert backend.last_error is not None


def test_hybrid_accepts_reasonable_length_polish(profile):
    """A polish that's a bit shorter than the original (tighter prose) but
    not drastically so should still be trusted."""
    from promptsmith.core.models import _apply_rules
    backend = HybridBackend()
    rule_based = _apply_rules("a product card", profile)
    # A polish at ~70% of the real rule-based baseline length - should NOT
    # be treated as degenerate (threshold is 50%).
    target_len = int(len(rule_based) * 0.7)
    reasonable_polish = ("A React product card built by a technical engineer, "
                          "with tests and graceful error handling throughout. " * 3)[:target_len]
    with patch.object(LLMBasedBackend, "refine", return_value=reasonable_polish):
        result = backend.refine("a product card", profile)
    assert result == reasonable_polish


def test_hybrid_falls_back_when_llm_returns_none_from_truncated_thinking(profile):
    """End-to-end integration: LLMBasedBackend.refine() now returns None for
    a truncated <think> block (see test_llm_backend.py), and HybridBackend
    must fall back to the rule-based text in that case, same as any other
    LLM failure - never surface an empty/unusable result."""
    backend = HybridBackend()

    with patch.object(LLMBasedBackend, "refine", return_value=None):
        result = backend.refine("a product card", profile)

    assert result is not None
    assert "React Developer" in result
    assert "React" in result and "TypeScript" in result
    assert "Include tests." in result
