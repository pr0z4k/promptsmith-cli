"""Tests for the Intent Compiler Pipeline."""

import pytest
from pathlib import Path
import tempfile
import yaml

from promptsmith.core.pipeline import IntentCompiler, IntentCompilationResult
from promptsmith.core.refiner import PromptRefiner
from promptsmith.core.profiles import ProfileManager
from promptsmith.core.templates import TemplateManager


@pytest.fixture
def temp_profiles_dir():
    """Create a temporary profiles directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profiles_dir = Path(tmpdir) / "profiles"
        profiles_dir.mkdir()
        
        # Create a test profile
        profile_data = {
            "name": "Test Profile",
            "role": "Test Role",
            "domain": ["Testing"],
            "tone": "neutral",
            "format": "text",
            "constraints": ["Be concise"],
        }
        profile_path = profiles_dir / "test.yaml"
        with open(profile_path, "w") as f:
            yaml.dump(profile_data, f)
        
        yield profiles_dir


@pytest.fixture
def temp_templates_dir():
    """Create a temporary templates directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        templates_dir = Path(tmpdir) / "templates"
        templates_dir.mkdir()
        
        # Create a test template
        template_data = {
            "name": "Test Template",
            "description": "A test template",
            "prompt": "Test prompt for {topic}",
        }
        template_path = templates_dir / "test.yaml"
        with open(template_path, "w") as f:
            yaml.dump(template_data, f)
        
        yield templates_dir


@pytest.fixture
def refiner(temp_profiles_dir, temp_templates_dir):
    """Create a refiner with test profiles and templates."""
    profile_manager = ProfileManager(temp_profiles_dir)
    template_manager = TemplateManager(temp_templates_dir)
    return PromptRefiner(profile_manager, template_manager)


@pytest.fixture
def compiler(refiner):
    """Create an IntentCompiler instance."""
    return IntentCompiler(refiner)


class TestIntentCompiler:
    """Test IntentCompiler functionality."""
    
    def test_compiler_initialization(self, refiner):
        """Test IntentCompiler initialization."""
        compiler = IntentCompiler(refiner)
        assert compiler.refiner == refiner
        assert compiler.analyzer is not None
    
    def test_compile_basic(self, compiler):
        """Test basic compilation."""
        result = compiler.compile("Explain Python")
        
        assert isinstance(result, IntentCompilationResult)
        assert result.original_prompt == "Explain Python"
        assert result.analysis is not None
        assert result.refined_prompt is not None
        assert len(result.steps) > 0
    
    def test_compile_with_profile(self, compiler):
        """Test compilation with specific profile."""
        result = compiler.compile(
            "Explain Python",
            profile_name="general"
        )
        
        assert result.original_prompt == "Explain Python"
        assert result.analysis is not None
    
    def test_compile_with_template(self, compiler):
        """Test compilation with template."""
        result = compiler.compile(
            "Python tutorial",
            template_name=None  # No template available in test
        )
        assert result.refined_prompt is not None
    
    def test_compile_empty_prompt(self, compiler):
        """Test compilation of empty prompt."""
        result = compiler.compile("")
        
        assert result.original_prompt == ""
        assert result.analysis.score == 0
        assert not result.is_ready
    
    def test_compile_and_refine(self, compiler):
        """Test compile_and_refine convenience method."""
        result = compiler.compile_and_refine("Explain Python")
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_get_analysis_only(self, compiler):
        """Test get_analysis_only method."""
        analysis = compiler.get_analysis_only("Explain Python")
        
        assert analysis is not None
        assert analysis.score > 0
    
    def test_compilation_steps(self, compiler):
        """Test that compilation includes all expected steps."""
        result = compiler.compile("Explain Python")
        
        step_names = [step.name for step in result.steps]
        
        assert "analysis" in step_names
        assert "readiness" in step_names
        assert "recommendations" in step_names
        assert "profile_selection" in step_names
        assert "preparation" in step_names
    
    def test_step_status(self, compiler):
        """Test step status tracking."""
        result = compiler.compile("Explain Python")
        
        for step in result.steps:
            assert step.status in ["completed", "processing", "failed"]
    
    def test_compilation_score(self, compiler):
        """Test compilation score calculation."""
        result = compiler.compile("Explain Python")
        
        assert 0 <= result.compilation_score <= 100
    
    def test_ready_compilation(self, compiler):
        """Test compilation of a ready prompt."""
        prompt = "As a senior developer, write comprehensive documentation in markdown format. This must include all essential information."
        result = compiler.compile(prompt)
        
        # Should have higher score
        assert result.analysis.score >= 50
    
    def test_not_ready_compilation(self, compiler):
        """Test compilation of a not-ready prompt."""
        result = compiler.compile("help")
        
        assert not result.is_ready or result.analysis.score < 80


class TestIntentCompilationResult:
    """Test IntentCompilationResult methods."""
    
    def test_get_summary(self, compiler):
        """Test get_summary method."""
        result = compiler.compile("Explain Python")
        summary = result.get_summary()
        
        assert isinstance(summary, str)
        assert "Compilation Score" in summary
        assert "Type" in summary
        assert "Profile" in summary
        assert "Readiness" in summary
    
    def test_get_step_status(self, compiler):
        """Test get_step_status method."""
        result = compiler.compile("Explain Python")
        
        status = result.get_step_status("analysis")
        assert status in ["completed", "processing", "failed"]
    
    def test_get_step_result(self, compiler):
        """Test get_step_result method."""
        result = compiler.compile("Explain Python")
        
        analysis_result = result.get_step_result("analysis")
        assert analysis_result is not None
    
    def test_get_nonexistent_step(self, compiler):
        """Test getting a nonexistent step."""
        result = compiler.compile("Explain Python")
        
        status = result.get_step_status("nonexistent")
        assert status is None
        
        result_data = result.get_step_result("nonexistent")
        assert result_data is None


class TestPipelineIntegration:
    """Test pipeline integration with refiner."""
    
    def test_pipeline_with_refiner(self, refiner):
        """Test that pipeline integrates with refiner."""
        compiler = IntentCompiler(refiner)
        result = compiler.compile("Explain Python")
        
        # The refined prompt should be different from analysis
        assert result.refined_prompt is not None
        assert len(result.refined_prompt) > 0
    
    def test_pipeline_error_handling(self, refiner):
        """Test pipeline error handling."""
        compiler = IntentCompiler(refiner)
        
        # Should handle empty prompts gracefully
        result = compiler.compile("")
        assert result.refined_prompt == ""
        assert not result.is_ready


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_compile_prompt_function(self, refiner):
        """Test compile_prompt convenience function."""
        from promptsmith.core.pipeline import compile_prompt
        
        result = compile_prompt("Explain Python", refiner)
        
        assert isinstance(result, IntentCompilationResult)
        assert result.original_prompt == "Explain Python"


def test_auto_recommended_profile_is_actually_applied(tmp_path):
    """Regression test for an independent review's finding: when no
    profile_name is passed explicitly, IntentCompiler falls back to
    analysis.recommended_profile, which is a human-readable display name
    ('React Developer') from PromptAnalyzer.TYPE_PROFILE_MAP - not the
    file id ('react-developer') that profile lookup actually keys on.
    This made every auto-recommended-profile compile() call fail lookup,
    get caught, and silently return the ORIGINAL unmodified prompt with
    only a warning to show for it - the profile was never applied. This
    is the pipeline's own documented main entry point, not some obscure
    internal path."""
    profiles_dir = tmp_path / "profiles"
    templates_dir = tmp_path / "templates"
    profiles_dir.mkdir()
    templates_dir.mkdir()

    (profiles_dir / "react-developer.yaml").write_text(yaml.dump({
        "name": "React Developer", "role": "React Developer",
        "domain": ["React", "Hooks"], "tone": "Technical",
        "format": "Markdown", "constraints": ["Use functional components."],
        "vendor": "generic", "backend": "rule",
    }))

    pm = ProfileManager(profiles_dir)
    tm = TemplateManager(templates_dir)
    refiner = PromptRefiner(pm, tm)
    compiler = IntentCompiler(refiner)

    result = compiler.compile(
        "Create a reusable React component with hooks for a login form"
    )

    assert result.analysis.recommended_profile == "React Developer"
    assert result.warnings == [], f"Expected no warnings, got: {result.warnings}"
    assert result.refined_prompt != result.original_prompt
    assert "Use functional components." in result.refined_prompt
