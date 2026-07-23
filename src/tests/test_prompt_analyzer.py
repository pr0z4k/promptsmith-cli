"""Tests for the PromptAnalyzer module."""

import pytest
from promptsmith.core.prompt_analyzer import (
    PromptAnalyzer,
    PromptAnalysis,
    PromptSmell,
    PromptRecommendation,
)


@pytest.fixture
def analyzer():
    """Create a fresh PromptAnalyzer for each test."""
    return PromptAnalyzer()


class TestPromptAnalyzerBasic:
    """Test basic analyzer functionality."""
    
    def test_empty_prompt(self, analyzer):
        """Test analysis of empty prompt."""
        result = analyzer.analyze("")
        assert result.score == 0
        assert result.detected_type == "empty"
        assert not result.is_ready
        assert "empty" in result.readiness_reason.lower()
    
    def test_whitespace_only_prompt(self, analyzer):
        """Test analysis of whitespace-only prompt."""
        result = analyzer.analyze("   \n  \t  ")
        assert result.score == 0
        assert result.detected_type == "empty"
    
    def test_simple_prompt(self, analyzer):
        """Test analysis of a simple prompt."""
        result = analyzer.analyze("Explain Python to me")
        assert result.score > 0
        assert result.score < 100  # Should have issues
        assert result.detected_type == "coding"
        assert not result.is_ready
    
    def test_analysis_returns_correct_type(self, analyzer):
        """Test that analysis returns PromptAnalysis."""
        result = analyzer.analyze("Hello")
        assert isinstance(result, PromptAnalysis)


class TestTypeDetection:
    """Test prompt type detection."""
    
    def test_detect_coding_type(self, analyzer):
        """Test detection of coding prompts."""
        prompts = [
            "Write a Python function to sort a list",
            "Java implementation of binary search",
            "Fix this JavaScript bug",
            "Write code for the API endpoint",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "coding"
    
    def test_detect_aem_type(self, analyzer):
        """Test detection of AEM prompts."""
        prompts = [
            "Create an AEM component for user profile",
            "Sling model for data fetching",
            "JCR query for content search",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "aem"
    
    def test_detect_nextjs_type(self, analyzer):
        """Test detection of NextJS prompts."""
        prompts = [
            "Create a NextJS app with app router",
            "Server component for data fetching",
            "getServerSideProps example",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "nextjs"
    
    def test_detect_react_type(self, analyzer):
        """Test detection of React prompts."""
        prompts = [
            "Create a React component with hooks",
            "useState and useEffect example",
            "React functional component",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "react"
    
    def test_detect_architecture_type(self, analyzer):
        """Test detection of architecture prompts."""
        prompts = [
            "Design a microservice architecture",
            "System design for ecommerce platform",
            "Component diagram for the application",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "architecture"
    
    def test_detect_documentation_type(self, analyzer):
        """Test detection of documentation prompts."""
        prompts = [
            "Write documentation for the API",
            "Create a README for this project",
            "Write a tutorial for the installation process",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "documentation"
    
    def test_detect_general_type(self, analyzer):
        """Test fallback to general type."""
        result = analyzer.analyze("Tell me a story")
        # Should fall back to general or another type
        assert result.detected_type in ["general", "email"]


class TestSmellDetection:
    """Test smell detection in prompts."""
    
    def test_detect_ambiguous_terms(self, analyzer):
        """Test detection of ambiguous terms."""
        ambiguous_terms = ["modern", "best", "optimize", "simple", "fast", "good"]
        
        for term in ambiguous_terms:
            result = analyzer.analyze(f"Give me a {term} solution")
            smell_terms = [s.term for s in result.smells]
            assert term in smell_terms
    
    def test_smell_has_explanation(self, analyzer):
        """Test that smells include explanations."""
        result = analyzer.analyze("This needs to be optimized")
        for smell in result.smells:
            assert smell.term
            assert smell.explanation
            assert smell.severity in ["low", "medium", "high"]
            assert smell.suggestion
    
    def test_high_severity_smells(self, analyzer):
        """Test detection of high-severity smells."""
        high_severity_terms = ["best", "optimize", "better"]
        
        for term in high_severity_terms:
            result = analyzer.analyze(f"Give me the {term} approach")
            high_smells = [s for s in result.smells if s.severity == "high"]
            assert any(term in s.term for s in high_smells)


class TestMissingElements:
    """Test detection of missing elements."""
    
    def test_missing_context(self, analyzer):
        """Test detection of missing context."""
        result = analyzer.analyze("Do it")
        assert "Context" in result.missing
    
    def test_missing_audience(self, analyzer):
        """Test detection of missing audience/role."""
        result = analyzer.analyze("Write some code")
        assert "Audience/Role" in result.missing
    
    def test_missing_output_format(self, analyzer):
        """Test detection of missing output format."""
        result = analyzer.analyze("Explain Python")
        assert "Output Format" in result.missing
    
    def test_complete_prompt(self, analyzer):
        """Test that a complete prompt has fewer missing elements."""
        prompt = "As a senior developer with background in Python, write a comprehensive guide on Python best practices in markdown format with code examples. The purpose is to educate junior developers on best practices."
        result = analyzer.analyze(prompt)
        # Should have fewer missing elements
        assert "Audience/Role" not in result.missing
        # Context should be present via "background"
        assert "Audience/Role" not in result.missing


class TestRecommendations:
    """Test recommendation generation."""
    
    def test_recommendations_generated(self, analyzer):
        """Test that recommendations are generated."""
        result = analyzer.analyze("Explain Python")
        assert len(result.recommendations) > 0
    
    def test_recommendation_structure(self, analyzer):
        """Test that recommendations have proper structure."""
        result = analyzer.analyze("Explain Python")
        for rec in result.recommendations:
            assert isinstance(rec, PromptRecommendation)
            assert rec.category
            assert rec.description
            assert rec.action
            assert 1 <= rec.priority <= 5
    
    def test_type_specific_recommendations(self, analyzer):
        """Test type-specific recommendations."""
        result = analyzer.analyze("Write a Python function")
        categories = [r.category for r in result.recommendations]
        assert "coding" in categories


class TestProfileRecommendation:
    """Test profile recommendation."""
    
    def test_recommend_profile_by_type(self, analyzer):
        """Test that profiles are recommended based on type."""
        result = analyzer.analyze("Create an AEM component")
        assert result.recommended_profile == "AEM Developer"
        
        result = analyzer.analyze("Write a NextJS app")
        assert result.recommended_profile == "NextJS Developer"
        
        result = analyzer.analyze("Design a system architecture")
        assert result.recommended_profile == "Solution Architect"
    
    def test_recommend_profile_with_current(self, analyzer):
        """Test that current profile is preferred when provided."""
        result = analyzer.analyze("Create an AEM component", current_profile="General")
        # Should still recommend AEM Developer based on content
        assert result.recommended_profile == "AEM Developer"


class TestReadinessAssessment:
    """Test readiness assessment."""
    
    def test_ready_prompt(self, analyzer):
        """Test a ready prompt."""
        prompt = "As a senior Python developer, write a comprehensive, production-ready implementation of a binary search algorithm in Python. The code must be well-documented, include unit tests, and follow PEP 8 guidelines. Format the response as markdown with code blocks."
        result = analyzer.analyze(prompt)
        # With enough detail, should be ready or close
        assert result.score >= 70
    
    def test_not_ready_prompt(self, analyzer):
        """Test a not-ready prompt."""
        result = analyzer.analyze("Do it")
        assert not result.is_ready
    
    def test_readiness_reason(self, analyzer):
        """Test that readiness reason is provided."""
        result = analyzer.analyze("Do it")
        assert result.readiness_reason
        assert "Not ready" in result.readiness_reason or "too short" in result.readiness_reason


class TestScoring:
    """Test score calculation."""
    
    def test_score_range(self, analyzer):
        """Test that scores are in valid range."""
        prompts = [
            "",
            "Hi",
            "Explain Python",
            "As a senior developer, write a comprehensive guide on Python best practices in markdown format with code examples and tests",
        ]
        for prompt in prompts:
            result = analyzer.analyze(prompt)
            assert 0 <= result.score <= 100
    
    def test_high_score_for_good_prompt(self, analyzer):
        """Test that good prompts get high scores."""
        prompt = "As a senior Python developer, write a comprehensive, production-ready implementation of a REST API endpoint. The code must follow best practices, include proper error handling, and be well-documented. Format the response as markdown with code blocks."
        result = analyzer.analyze(prompt)
        assert result.score >= 70
    
    def test_low_score_for_poor_prompt(self, analyzer):
        """Test that poor prompts get low scores."""
        result = analyzer.analyze("help")
        assert result.score < 50


class TestAnalysisSummary:
    """Test analysis summary methods."""
    
    def test_get_readiness_percentage(self, analyzer):
        """Test get_readiness_percentage method."""
        result = analyzer.analyze("Test prompt")
        percentage = result.get_readiness_percentage()
        assert 0 <= percentage <= 100
    
    def test_get_summary(self, analyzer):
        """Test get_summary method."""
        result = analyzer.analyze("Test prompt")
        summary = result.get_summary()
        assert isinstance(summary, str)
        assert "Readiness" in summary
        assert "Type" in summary
        assert "Profile" in summary


class TestTeamSpecificPatterns:
    """Test patterns specific to the Customer Portal team."""
    
    def test_aem_specific_detection(self, analyzer):
        """Test AEM-specific pattern detection."""
        result = analyzer.analyze("Create a Sling model for content retrieval")
        assert result.detected_type == "aem"
        assert result.recommended_profile == "AEM Developer"
    
    def test_nextjs_aem_detection(self, analyzer):
        """Test NextJS+AEM detection."""
        result = analyzer.analyze("NextJS app with AEM Headless GraphQL")
        assert result.detected_type in ["nextjs", "nextjs-aem"]
    
    def test_customer_portal_detection(self, analyzer):
        """Test Customer Portal detection."""
        result = analyzer.analyze("Design the customer portal architecture")
        assert result.detected_type == "customer-portal"
        assert result.recommended_profile == "Customer Portal Architect"
    
    def test_react_aem_detection(self, analyzer):
        """Test React+AEM detection."""
        result = analyzer.analyze("React component for AEM SPA Editor")
        assert result.detected_type in ["react", "react-aem"]


class TestEdgeCases:
    """Test edge cases."""
    
    def test_very_long_prompt(self, analyzer):
        """Test very long prompt handling."""
        long_prompt = "As a senior developer, " * 100
        result = analyzer.analyze(long_prompt)
        assert result.score <= 100
    
    def test_unicode_prompt(self, analyzer):
        """Test unicode prompt handling."""
        result = analyzer.analyze("Explain Python en français")
        assert result.score > 0
    
    def test_case_insensitive_detection(self, analyzer):
        """Test case-insensitive type detection."""
        result1 = analyzer.analyze("create an AEM component")
        result2 = analyzer.analyze("CREATE AN AEM COMPONENT")
        assert result1.detected_type == result2.detected_type
    
    def test_special_characters(self, analyzer):
        """Test prompts with special characters."""
        result = analyzer.analyze("Write code for API @ /api/v1/users")
        assert result.score > 0


class TestFalsePositiveRegression:
    """Regression tests for two bug classes found in review: (1) short
    patterns matching as substrings inside unrelated words (no word
    boundaries), and (2) generic single-word matches misclassifying
    unrelated prompts. Both previously caused confident, wrong type
    detection on prompts with nothing to do with the assigned type."""

    def test_no_substring_match_inside_unrelated_words(self, analyzer):
        """Short patterns like 'api', 'cq', 'roi' must not match when
        embedded inside unrelated words ('capital', 'acquire', 'heroic')."""
        cases = [
            "The capital allocation needs review",  # 'api' inside 'capital'
            "We need to acquire new office chairs",  # 'cq' inside 'acquire'
            "Tell me a heroic story about a firefighter",  # 'roi' inside 'heroic'
        ]
        for prompt in cases:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "general", (
                f"{prompt!r} should not match via an embedded substring, "
                f"got {result.detected_type!r}"
            )

    def test_generic_words_dont_misclassify(self, analyzer):
        """Common English words that happen to appear in type patterns
        ('state', 'method', 'notes', 'estimate', 'budget', 'design')
        must not confidently misclassify unrelated everyday prompts."""
        cases = [
            "Describe the current state of our quarterly sales figures",
            "What is the best method to bake bread",
            "Take notes during the meeting",
            "Estimate how long the flight will take",
            "Review our budget for the school fundraiser",
            "Explain the design of the new office building",
            "List the props needed for the theater production",
        ]
        for prompt in cases:
            result = analyzer.analyze(prompt)
            assert result.detected_type == "general", (
                f"{prompt!r} should fall back to general, "
                f"got {result.detected_type!r} -> {result.recommended_profile!r}"
            )

    def test_genuine_signals_still_detected(self, analyzer):
        """Sanity check: the fixes above must not have made detection too
        conservative - clear, genuine signals should still classify correctly."""
        cases = [
            ("Build a React component with hooks and useState", "react"),
            ("Design an AEM Sling model for content fragments", "aem"),
            ("Write a Python function to refactor this algorithm", "coding"),
            ("Create API documentation with a user guide and readme", "documentation"),
            ("Plan our next sprint with a timeline and milestones", "planning"),
        ]
        for prompt, expected_type in cases:
            result = analyzer.analyze(prompt)
            assert result.detected_type == expected_type, (
                f"{prompt!r} should detect as {expected_type!r}, "
                f"got {result.detected_type!r}"
            )

    def test_all_recommended_profiles_exist_on_disk(self):
        """Every profile name the analyzer can recommend must correspond to
        an actual profile file, or the UI suggests something unselectable."""
        from promptsmith.core.prompt_analyzer import PromptAnalyzer as PA
        from promptsmith.utils.path_utils import get_asset_path

        # Resolve through the same path logic the app itself uses, so this
        # test keeps guarding the real UI behavior wherever built-ins live.
        profiles_dir = get_asset_path("profiles", __file__)
        real_slugs = {p.stem for p in profiles_dir.glob("*.yaml")}

        recommended_names = {name for name in PA.TYPE_PROFILE_MAP.values()}
        for name in recommended_names:
            slug = name.lower().replace(" ", "-")
            assert slug in real_slugs, (
                f"Recommended profile {name!r} (slug {slug!r}) has no "
                f"matching profile file - the UI would suggest something "
                f"the user cannot actually select"
            )


class TestChallenges:
    """Tests for the Challenge step: deterministic clarifying questions,
    informational only, applies regardless of profile/template/backend."""

    def test_scope_challenge_fires_on_vague_flexibility_words(self, analyzer):
        result = analyzer.analyze("Create a reusable card component with an image and price.")
        categories = [c.category for c in result.challenges]
        assert "scope" in categories

    def test_scope_challenge_does_not_fire_without_scope_words(self, analyzer):
        result = analyzer.analyze(
            "Create a card component for the homepage that shows an image, "
            "title, and price, tested with Jest for a frontend developer."
        )
        categories = [c.category for c in result.challenges]
        assert "scope" not in categories

    def test_success_criteria_challenge_fires_without_definition_of_done(self, analyzer):
        result = analyzer.analyze("Build a login form with email and password fields.")
        categories = [c.category for c in result.challenges]
        assert "success_criteria" in categories

    def test_success_criteria_challenge_does_not_fire_when_present(self, analyzer):
        result = analyzer.analyze(
            "Build a login form with email and password fields. "
            "Success criteria: valid credentials redirect to the dashboard, "
            "invalid credentials show an error, covered by unit tests."
        )
        categories = [c.category for c in result.challenges]
        assert "success_criteria" not in categories

    def test_audience_challenge_fires_without_audience(self, analyzer):
        result = analyzer.analyze("Write a summary of the quarterly results.")
        categories = [c.category for c in result.challenges]
        assert "audience" in categories

    def test_audience_challenge_does_not_fire_when_present(self, analyzer):
        result = analyzer.analyze("Write a summary of the quarterly results for the executive team.")
        categories = [c.category for c in result.challenges]
        assert "audience" not in categories

    def test_quantity_challenge_fires_on_vague_quantity(self, analyzer):
        result = analyzer.analyze("Add several new fields to the form for the sales team.")
        categories = [c.category for c in result.challenges]
        assert "quantity" in categories

    def test_quantity_challenge_does_not_fire_with_exact_number(self, analyzer):
        result = analyzer.analyze("Add 3 new fields to the form for the sales team.")
        categories = [c.category for c in result.challenges]
        assert "quantity" not in categories

    def test_integration_challenge_fires_without_existing_system_constraints(self, analyzer):
        result = analyzer.analyze("Extend the existing dashboard for the reporting team.")
        categories = [c.category for c in result.challenges]
        assert "integration" in categories

    def test_integration_challenge_does_not_fire_when_constraints_given(self, analyzer):
        result = analyzer.analyze(
            "Extend the existing dashboard, which is built with React 18 and "
            "follows our internal style guide, for the reporting team."
        )
        categories = [c.category for c in result.challenges]
        assert "integration" not in categories

    def test_integration_challenge_does_not_fire_without_integration_words(self, analyzer):
        """Shouldn't fire just because constraint words are absent - only
        when there's also a signal this is extending something existing."""
        result = analyzer.analyze("Write a haiku about autumn for a poetry newsletter reader.")
        categories = [c.category for c in result.challenges]
        assert "integration" not in categories

    def test_challenges_never_affect_score_or_readiness(self, analyzer):
        """Challenges must be purely informational - identical score/readiness
        with or without triggering terms, all else equal."""
        with_challenge = analyzer.analyze(
            "Create a reusable card component for a frontend developer, "
            "success criteria: renders correctly, tested with unit tests."
        )
        without_challenge = analyzer.analyze(
            "Create a card component for a frontend developer, "
            "success criteria: renders correctly, tested with unit tests."
        )
        assert len(with_challenge.challenges) >= 1
        assert len(without_challenge.challenges) == 0
        assert with_challenge.score == without_challenge.score
        assert with_challenge.is_ready == without_challenge.is_ready

    def test_challenges_apply_regardless_of_current_profile(self, analyzer):
        """Challenge detection must not depend on which profile is passed -
        applies identically across every profile, not just vibe-coding."""
        prompt = "Create a reusable policy document."
        result_no_profile = analyzer.analyze(prompt, None)
        result_vibe_coding = analyzer.analyze(prompt, "vibe-coding")
        result_hr = analyzer.analyze(prompt, "hr-manager")
        categories_no_profile = {c.category for c in result_no_profile.challenges}
        categories_vibe = {c.category for c in result_vibe_coding.challenges}
        categories_hr = {c.category for c in result_hr.challenges}
        assert categories_no_profile == categories_vibe == categories_hr

    def test_challenges_are_backend_agnostic(self, analyzer):
        """Analysis (and therefore Challenges) happens before backend
        selection in the pipeline - PromptAnalyzer has no notion of backend
        at all, so this is structurally guaranteed, verified here directly."""
        import inspect
        sig = inspect.signature(analyzer.analyze)
        assert "backend" not in sig.parameters

    def test_challenge_has_question_reason_and_category(self, analyzer):
        result = analyzer.analyze("Create a reusable card component.")
        assert len(result.challenges) > 0
        for c in result.challenges:
            assert c.question
            assert c.reason
            assert c.category


class TestCombinedTechnologyTypeDetection:
    """Regression tests for an independent review's finding: type
    detection was brittle for combined technologies - a prompt mentioning
    both AEM and Next.js could be misclassified as plain 'aem' if it
    didn't happen to use one of the explicit multi-word compound patterns
    ('nextjs aem', 'aem nextjs'), because a single highly-specific
    single-tech phrase match (e.g. 'aem component', weight 2) could
    outscore the combined type's own weight sum even when both
    technologies were clearly, independently present."""

    def test_separately_phrased_nextjs_and_aem_still_detected_as_combined(self, analyzer):
        """The exact reported case: technologies phrased separately, not
        as one of the compound patterns, previously lost to plain 'aem'
        because 'aem component' (weight 2) outscored the combined type's
        own raw sum."""
        t, _ = analyzer._detect_type(
            "create an aem component using graphql content fragments in next.js"
        )
        assert t == "nextjs-aem"

    def test_compound_phrasing_still_works(self, analyzer):
        t, _ = analyzer._detect_type(
            "build a next.js aem headless component using content fragments"
        )
        assert t == "nextjs-aem"

    def test_react_aem_combined_detection(self, analyzer):
        t, _ = analyzer._detect_type("build a react aem spa editor component")
        assert t == "react-aem"

    def test_pure_single_technology_prompts_unaffected(self, analyzer):
        """Sanity check: prompts about only one technology must not be
        pulled toward a combined type just because the fix exists."""
        assert analyzer._detect_type("create a react component with hooks")[0] == "react"
        assert analyzer._detect_type("build an aem sling model for content management")[0] == "aem"
        assert analyzer._detect_type("build a nextjs app with server components")[0] == "nextjs"
