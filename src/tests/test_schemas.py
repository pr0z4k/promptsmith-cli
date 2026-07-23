"""Tests for PromptSmith's lightweight schema validation."""
import pytest
from promptsmith.core.schemas import (
    ProfileSchema,
    TemplateSchema,
    validate_profile,
    validate_template,
)


def test_profile_schema_valid():
    data = {
        "name": "Test Profile",
        "role": "Tester",
        "domain": ["Testing", "QA"],
        "tone": "professional",
        "format": "markdown",
        "constraints": ["Be thorough", "Be accurate"],
        "vendor": "generic",
        "version": 1,
    }
    profile = ProfileSchema.validate(data, "test.yaml")
    assert profile["name"] == "Test Profile"
    assert profile["role"] == "Tester"
    assert profile["domain"] == ["Testing", "QA"]


def test_profile_schema_minimal_fills_defaults():
    # Only required field is role; optional fields should be defaulted.
    data = {"role": "Developer"}
    profile = ProfileSchema.validate(data, "test.yaml")
    assert profile["role"] == "Developer"
    assert profile["domain"] == []
    assert profile["tone"] == "neutral"
    assert profile["format"] == "text"
    assert profile["constraints"] == []
    assert profile["version"] == 1
    assert profile["backend"] == "rule"


def test_profile_schema_missing_required():
    data = {"name": "Incomplete"}  # missing role
    with pytest.raises(ValueError):
        ProfileSchema.validate(data, "test.yaml")


def test_profile_schema_wrong_type():
    data = {"role": "Developer", "domain": "not-a-list"}
    with pytest.raises(ValueError):
        ProfileSchema.validate(data, "test.yaml")


def test_template_schema_valid():
    data = {
        "name": "Test Template",
        "description": "A test template",
        "prompt": "Test prompt for {topic}",
        "version": 1,
    }
    template = TemplateSchema.validate(data, "test.yaml")
    assert template["name"] == "Test Template"
    assert template["prompt"] == "Test prompt for {topic}"


def test_template_schema_minimal_fills_defaults():
    # Only required field is prompt.
    data = {"prompt": "Hello {name}"}
    template = TemplateSchema.validate(data, "test.yaml")
    assert template["prompt"] == "Hello {name}"
    assert template["version"] == 1


def test_template_schema_missing_required():
    data = {"name": "Incomplete"}  # missing prompt
    with pytest.raises(ValueError):
        TemplateSchema.validate(data, "test.yaml")


def test_validate_profile_success():
    data = {"role": "Developer"}
    result = validate_profile(data, "test.yaml")
    assert result["role"] == "Developer"


def test_validate_profile_failure():
    data = {}  # missing role
    with pytest.raises(ValueError) as exc_info:
        validate_profile(data, "test.yaml")
    assert "missing required fields" in str(exc_info.value)


def test_validate_template_success():
    data = {"prompt": "Hello {name}"}
    result = validate_template(data, "test.yaml")
    assert result["prompt"] == "Hello {name}"


def test_validate_template_failure():
    data = {}  # missing prompt
    with pytest.raises(ValueError) as exc_info:
        validate_template(data, "test.yaml")
    assert "missing required fields" in str(exc_info.value)


def test_validate_profile_rejects_non_string_domain_items():
    """Regression test for an independent review's finding: schema
    validation checked that 'domain' was a list, but not that every item
    inside it was a string. A profile like domain: ["Testing", 123, null]
    passed validation cleanly and only crashed later, deep inside
    _apply_rules(), with an opaque AttributeError ('int' object has no
    attribute 'lower') - far from the actual malformed source file."""
    data = {
        "role": "Tester",
        "domain": ["Testing", 123, None],
    }
    with pytest.raises(ValueError) as exc_info:
        validate_profile(data, "test.yaml")
    assert "domain" in str(exc_info.value)
    assert "string" in str(exc_info.value).lower()


def test_validate_profile_rejects_non_string_constraints_items():
    data = {
        "role": "Tester",
        "constraints": ["Be concise", 42],
    }
    with pytest.raises(ValueError) as exc_info:
        validate_profile(data, "test.yaml")
    assert "constraints" in str(exc_info.value)


def test_validate_profile_rejects_non_string_role():
    data = {"role": 123}
    with pytest.raises(ValueError) as exc_info:
        validate_profile(data, "test.yaml")
    assert "role" in str(exc_info.value)


def test_validate_profile_accepts_well_formed_string_lists():
    """Sanity check: normal, correctly-typed profiles are unaffected."""
    data = {
        "role": "Tester",
        "domain": ["Testing", "QA"],
        "constraints": ["Be concise", "Include examples"],
    }
    result = validate_profile(data, "test.yaml")
    assert result["domain"] == ["Testing", "QA"]
    assert result["constraints"] == ["Be concise", "Include examples"]
