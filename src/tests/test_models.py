"""Tests for model backends."""
import pytest
from pathlib import Path
from promptsmith.core.backends.rule_based import RuleBasedBackend
from promptsmith.core.models import _apply_rules


@pytest.fixture
def rule_backend():
    return RuleBasedBackend()


@pytest.fixture
def sample_profile():
    return {
        "name": "Test Profile",
        "role": "Tester",
        "domain": ["Testing", "QA"],
        "tone": "professional",
        "format": "markdown",
        "constraints": ["Be thorough", "Be accurate"],
    }


def test_rule_based_backend_refine(rule_backend, sample_profile):
    """Test that rule-based backend applies rules correctly."""
    prompt = "Test prompt"
    result = rule_backend.refine(prompt, sample_profile)
    
    assert result is not None
    assert "Tester" in result  # Role should be injected
    assert "professional" in result  # Tone should be injected


def test_rule_based_backend_empty_profile(rule_backend):
    """Test rule-based backend with empty profile returns prompt unmodified."""
    prompt = "Test prompt"
    result = rule_backend.refine(prompt, {})

    assert result == prompt


def test_apply_rules_adds_role():
    """Test that _apply_rules adds role if missing."""
    profile = {"role": "Developer"}
    result = _apply_rules("Write code", profile)
    
    assert "Developer" in result


def test_apply_rules_adds_domain():
    """Test that _apply_rules adds domain if missing."""
    profile = {"role": "Developer", "domain": ["Python"]}
    result = _apply_rules("Write code", profile)
    
    assert "Python" in result


def test_apply_rules_domain_partial_match_only_appends_missing_terms():
    """Regression test: previously, if even ONE domain term already
    appeared anywhere in the text, the entire domain clause was skipped,
    silently dropping every other domain area that was never mentioned.
    Confirmed in production: a response mentioning only 'Testing' caused
    'Software Engineering, Architecture, Refactoring, Code Quality' to
    vanish entirely on a second refinement pass. Only the terms genuinely
    missing should be appended - the ones already present should be left
    alone, not silently discarded."""
    profile = {
        "role": "Engineer",
        "domain": ["Software Engineering", "Architecture", "Testing", "Refactoring", "Code Quality"],
    }
    # Body already mentions "Testing" but none of the other four domain areas
    text = "This section covers Testing thoroughly with unit tests."
    result = _apply_rules(text, profile)

    for term in ["Software Engineering", "Architecture", "Refactoring", "Code Quality"]:
        assert term in result, f"{term!r} should have been appended since it was never mentioned"

    # "Testing" should appear (it's in the original text) but should NOT be
    # duplicated in the appended "Focus on ..." clause
    focus_clause = result.split("Focus on", 1)[1] if "Focus on" in result else ""
    assert "Testing" not in focus_clause


def test_apply_rules_adds_tone():
    """Test that _apply_rules adds tone if missing."""
    profile = {"role": "Developer", "tone": "friendly"}
    result = _apply_rules("Write code", profile)
    
    assert "friendly" in result


def test_apply_rules_adds_format():
    """Test that _apply_rules adds format if missing."""
    profile = {"role": "Developer", "format": "JSON"}
    result = _apply_rules("Write code", profile)
    
    assert "JSON" in result


def test_apply_rules_adds_constraints():
    """Test that _apply_rules adds constraints."""
    profile = {
        "role": "Developer",
        "constraints": ["Use TypeScript", "Add tests"],
    }
    result = _apply_rules("Write code", profile)
    
    assert "Use TypeScript" in result
    assert "Add tests" in result


def test_apply_rules_pads_short_prompts():
    """Test that _apply_rules pads short prompts."""
    profile = {"role": "Developer"}
    result = _apply_rules("Do it", profile)
    
    assert result.startswith("Please")


def test_apply_rules_preserves_existing_content():
    """Test that _apply_rules doesn't duplicate existing content."""
    profile = {"role": "Developer", "domain": ["Python"]}
    result = _apply_rules("Write Python code for web scraping", profile)
    
    # Should not add "Python" again since it's already in the prompt
    assert result.count("Python") == 1
