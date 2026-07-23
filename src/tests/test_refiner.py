import pytest
import yaml
from promptsmith.core.profiles import ProfileManager
from promptsmith.core.templates import TemplateManager
from promptsmith.core.refiner import PromptRefiner
from promptsmith.core.backends.rule_based import RuleBasedBackend


@pytest.fixture
def refiner(tmp_path):
    pdir = tmp_path / "profiles"
    tdir = tmp_path / "templates"
    pdir.mkdir(); tdir.mkdir()

    (pdir / "test-profile.yaml").write_text(yaml.dump({
        "name": "Test", "role": "Tester",
        "domain": ["Testing"], "tone": "Neutral",
        "format": "Text", "constraints": ["Be concise"],
    }))
    (tdir / "test-template.yaml").write_text(yaml.dump({
        "name": "Test Template",
        "description": "A test template",
        "prompt": "Test prompt for {topic}",
    }))

    return PromptRefiner(
        ProfileManager(pdir),
        TemplateManager(tdir),
    )


def test_rule_based_adds_role(refiner):
    refined = refiner.refine("Explain testing", "test-profile")
    assert "Tester" in refined


def test_rule_based_adds_tone(refiner):
    refined = refiner.refine("Explain testing", "test-profile")
    assert "Neutral" in refined


def test_template_substitution(refiner):
    refined = refiner.refine("unit tests", "test-profile", "test-template")
    assert "unit tests" in refined
    assert "Test prompt for" in refined


def test_empty_prompt_is_padded(refiner):
    refined = refiner.refine("do it", "test-profile")
    assert refined.startswith("Please")


@pytest.fixture
def hybrid_refiner(tmp_path):
    """A profile with multiple domain areas, backend set to hybrid, for
    testing the completeness guarantee against a polish that drops some
    (but not all) of them - the exact production scenario this guards."""
    pdir = tmp_path / "profiles"
    tdir = tmp_path / "templates"
    pdir.mkdir(); tdir.mkdir()

    (pdir / "hybrid-profile.yaml").write_text(yaml.dump({
        "name": "Hybrid Test", "role": "Senior Engineer",
        "domain": ["Software Engineering", "Architecture", "Testing", "Refactoring", "Code Quality"],
        "tone": "Pragmatic", "format": "Markdown",
        "constraints": ["Include tests.", "Handle errors properly."],
        "backend": "hybrid",
    }))

    return PromptRefiner(
        ProfileManager(pdir),
        TemplateManager(tdir),
    )


def test_hybrid_completeness_survives_partial_llm_drop(hybrid_refiner, monkeypatch):
    """Regression test for a real production bug: HybridBackend's LLM
    polish step was trusted completely, with no verification. A polish
    that mentions only ONE of five domain areas (mirroring what actually
    happened: a response mentioning only 'Testing') must not cause the
    other four to be silently dropped from the final output - the whole
    point of hybrid is that this can never happen."""
    from promptsmith.core.backends.llm_backend import LLMBasedBackend

    polish_that_drops_most_domain_context = (
        "## Component Plan\n"
        "- Testing: write thorough unit tests for reliability.\n"
        "- Error handling: handle edge cases gracefully.\n"
        "- This section covers the core implementation approach in detail, "
        "with enough length to pass the degenerate-output check reliably."
    )

    def fake_refine(self, prompt, profile, polish_mode=False):
        return polish_that_drops_most_domain_context

    monkeypatch.setattr(LLMBasedBackend, "refine", fake_refine)

    result = hybrid_refiner.refine("build a widget", "hybrid-profile")

    for domain_term in ["Software Engineering", "Architecture", "Testing", "Refactoring", "Code Quality"]:
        assert domain_term in result, f"{domain_term!r} was silently dropped"
    for constraint in ["Include tests.", "Handle errors properly."]:
        assert constraint in result, f"{constraint!r} was silently dropped"
    assert hybrid_refiner.last_backend_used == "hybrid"


def test_hybrid_result_does_not_leak_raw_profile_framing(tmp_path, monkeypatch):
    """Regression test: reported bug where generating a React component
    under the adobe-experience-developer profile produced valid TSX/markdown
    followed by a leaked, verbatim tail of profile framing text ("Act as if
    I am Adobe Experience Manager (AEM) Developer. ... Use a Technical and
    precise tone. Format the response as ..."). This came from PromptRefiner
    re-running the full prompt-framing rules against already-generated LLM
    output. Domain/constraint completeness must still be guaranteed, but
    role/tone/format framing sentences must never appear in the result."""
    import yaml
    from promptsmith.core.backends.llm_backend import LLMBasedBackend

    pdir = tmp_path / "profiles"
    tdir = tmp_path / "templates"
    pdir.mkdir()
    tdir.mkdir()

    (pdir / "adobe-experience-developer.yaml").write_text(yaml.dump({
        "name": "Adobe Experience Developer",
        "role": "Adobe Experience Manager (AEM) Developer",
        "domain": ["AEM", "Content Management", "OSGi", "Sling", "JCR"],
        "tone": "Technical and precise",
        "format": "Code snippets for AEM components, markdown for explanations",
        "constraints": ["Reference AEM best practices (e.g., component design, templating)."],
        "vendor": "generic",
        "backend": "hybrid",
    }))

    refiner = PromptRefiner(ProfileManager(pdir), TemplateManager(tdir))

    # Generated content that already covers every domain/constraint term,
    # exactly like a real LLM-produced component + explanation would.
    generated_output = (
        "```typescript\n"
        "export default function ElasticData() { return null; }\n"
        "```\n"
        "This component targets AEM, using OSGi, Sling, and JCR for Content "
        "Management. Reference AEM best practices (e.g., component design, templating)."
    )

    def fake_refine(self, prompt, profile, polish_mode=False):
        return generated_output

    monkeypatch.setattr(LLMBasedBackend, "refine", fake_refine)

    result = refiner.refine(
        "Create a new react component to display elastic data in aem homepage",
        "adobe-experience-developer",
    )

    assert "Act as if I am" not in result
    assert "Use a Technical and precise tone" not in result
    assert "Format the response as" not in result
    assert result == generated_output
