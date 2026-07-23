"""
Intent Compiler Pipeline for PromptSmith-cli.

This module orchestrates the full intent compilation pipeline:
    Human Thought -> Analyzer -> Readiness -> Smells -> Recommendations -> Profiles -> Templates -> Preparation -> Output

The pipeline transforms ambiguous human intent into structured AI instructions
before any LLM inference occurs.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional
import logging

from .prompt_analyzer import PromptAnalyzer, PromptAnalysis, PromptRecommendation
from .refiner import PromptRefiner

logger = logging.getLogger(__name__)


@dataclass
class CompilationStep:
    """Represents a single step in the compilation pipeline."""
    name: str
    description: str
    status: str  # "pending", "processing", "completed", "failed"
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class IntentCompilationResult:
    """
    Complete result of the intent compilation pipeline.
    
    Contains all intermediate results and the final refined prompt.
    """
    original_prompt: str
    analysis: PromptAnalysis
    refined_prompt: str
    steps: List[CompilationStep] = field(default_factory=list)
    compilation_score: int = 0
    is_ready: bool = False
    readiness_reason: str = ""
    recommendations: List[PromptRecommendation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def get_summary(self) -> str:
        """Return a human-readable summary of the compilation result."""
        lines = []
        lines.append(f"Compilation Score: {self.compilation_score}/100")
        lines.append(f"Type: {self.analysis.detected_type}")
        lines.append(f"Profile: {self.analysis.recommended_profile}")
        lines.append(f"Readiness: {'READY' if self.is_ready else 'NOT READY'}")
        
        if self.readiness_reason:
            lines.append(f"Reason: {self.readiness_reason}")
        
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
            
        if self.recommendations:
            lines.append(f"Recommendations: {len(self.recommendations)}")
        
        return " | ".join(lines)
    
    def get_step_status(self, step_name: str) -> Optional[str]:
        """Get the status of a specific compilation step."""
        for step in self.steps:
            if step.name == step_name:
                return step.status
        return None
    
    def get_step_result(self, step_name: str) -> Optional[Any]:
        """Get the result of a specific compilation step."""
        for step in self.steps:
            if step.name == step_name:
                return step.result
        return None


class IntentCompiler:
    """
    Intent Compiler - The core pipeline orchestrator.
    
    Transforms ambiguous human intent into precise, structured AI instructions.
    This is the main implementation of the Intent Compiler architectural vision.
    
    Pipeline stages:
    1. Analysis: Detect type, smells, missing elements, generate recommendations
    2. Readiness: Assess if prompt is ready for AI
    3. Recommendation: Suggest profiles, templates, improvements
    4. Preparation: Apply profile, template, and rules to refine prompt
    5. Output: Return structured, ready-to-use prompt
    """
    
    def __init__(
        self,
        refiner: PromptRefiner,
        analyzer: Optional[PromptAnalyzer] = None,
    ):
        """
        Initialize the Intent Compiler.
        
        Args:
            refiner: The PromptRefiner instance for prompt preparation
            analyzer: Optional PromptAnalyzer instance (created if None)
        """
        self.refiner = refiner
        self.analyzer = analyzer or PromptAnalyzer()
        logger.info("Intent Compiler initialized")
    
    def compile(
        self,
        prompt: str,
        profile_name: Optional[str] = None,
        template_name: Optional[str] = None,
        auto_apply_recommendations: bool = False,
    ) -> IntentCompilationResult:
        """
        Compile human intent into a structured AI-ready prompt.
        
        This is the main entry point for the Intent Compiler pipeline.
        
        Args:
            prompt: The raw user prompt to compile
            profile_name: Optional profile name override
            template_name: Optional template name to use
            auto_apply_recommendations: If True, automatically apply simple fixes
            
        Returns:
            IntentCompilationResult with full pipeline output
        """
        steps = []
        warnings = []
        
        # Record original
        original_prompt = prompt
        
        # Step 1: Analysis
        logger.info("Pipeline Step 1: Analysis")
        analysis_step = CompilationStep(
            name="analysis",
            description="Analyze prompt for type, smells, missing elements, and recommendations",
            status="processing"
        )
        steps.append(analysis_step)
        
        try:
            analysis = self.analyzer.analyze(prompt, profile_name)
            analysis_step.status = "completed"
            analysis_step.result = analysis
            logger.info(f"Analysis complete: type={analysis.detected_type}, score={analysis.score}")
        except Exception as e:
            analysis_step.status = "failed"
            analysis_step.error = str(e)
            logger.error(f"Analysis failed: {e}")
            # Fallback: create minimal analysis
            analysis = PromptAnalysis(
                score=0,
                detected_type="unknown",
                missing=["Analysis failed"],
                recommended_profile="General",
                is_ready=False,
                readiness_reason=f"Analysis failed: {e}"
            )
            analysis_step.result = analysis
            warnings.append(f"Analysis failed: {e}")
        
        # Step 2: Readiness Assessment
        logger.info("Pipeline Step 2: Readiness Assessment")
        readiness_step = CompilationStep(
            name="readiness",
            description="Assess prompt readiness for AI inference",
            status="completed",
            result={
                "is_ready": analysis.is_ready,
                "reason": analysis.readiness_reason,
                "score": analysis.score
            }
        )
        steps.append(readiness_step)
        
        # Step 3: Recommendation Generation
        logger.info("Pipeline Step 3: Recommendation Generation")
        recommendation_step = CompilationStep(
            name="recommendations",
            description="Generate actionable recommendations for prompt improvement",
            status="completed",
            result=analysis.recommendations
        )
        steps.append(recommendation_step)
        
        # Step 4: Profile Selection
        logger.info("Pipeline Step 4: Profile Selection")
        profile_step = CompilationStep(
            name="profile_selection",
            description="Select or recommend the best profile for this prompt",
            status="completed",
            result={
                "selected_profile": profile_name or analysis.recommended_profile,
                "recommended_profile": analysis.recommended_profile
            }
        )
        steps.append(profile_step)
        
        # Determine final profile
        final_profile = profile_name or analysis.recommended_profile
        
        # Step 5: Preparation (Refinement)
        logger.info("Pipeline Step 5: Preparation")
        preparation_step = CompilationStep(
            name="preparation",
            description="Apply profile, template, and rules to prepare prompt",
            status="processing"
        )
        steps.append(preparation_step)
        
        try:
            # Apply auto-fixes if requested
            working_prompt = prompt
            if auto_apply_recommendations:
                working_prompt = self._auto_apply_recommendations(prompt, analysis)
            
            # Use refiner to apply profile and template
            refined_prompt = self.refiner.refine(
                working_prompt,
                profile_name=final_profile,
                template_name=template_name
            )
            preparation_step.status = "completed"
            preparation_step.result = refined_prompt
            logger.info("Preparation complete")
        except Exception as e:
            preparation_step.status = "failed"
            preparation_step.error = str(e)
            logger.error(f"Preparation failed: {e}")
            refined_prompt = prompt  # Fallback to original
            warnings.append(f"Preparation failed: {e}")
        
        # Calculate compilation score (weighted average)
        compilation_score = self._calculate_compilation_score(analysis, refined_prompt != prompt)
        
        # Final readiness
        is_ready = analysis.is_ready
        readiness_reason = analysis.readiness_reason
        
        # If preparation changed the prompt significantly, re-analyze
        if refined_prompt != prompt:
            # Quick re-check
            new_analysis = self.analyzer.analyze(refined_prompt, final_profile)
            if new_analysis.score > analysis.score:
                is_ready = new_analysis.is_ready
                readiness_reason = new_analysis.readiness_reason
                compilation_score = self._calculate_compilation_score(new_analysis, True)
        
        # Build final result
        result = IntentCompilationResult(
            original_prompt=original_prompt,
            analysis=analysis,
            refined_prompt=refined_prompt,
            steps=steps,
            compilation_score=compilation_score,
            is_ready=is_ready,
            readiness_reason=readiness_reason,
            recommendations=analysis.recommendations,
            warnings=warnings
        )
        
        logger.info(f"Intent compilation complete. Score: {compilation_score}/100, Ready: {is_ready}")
        return result
    
    def compile_and_refine(
        self,
        prompt: str,
        profile_name: Optional[str] = None,
        template_name: Optional[str] = None,
    ) -> str:
        """
        Convenience method: compile and return just the refined prompt.
        
        This is a simpler interface for callers that just want the result.
        
        Args:
            prompt: The raw user prompt
            profile_name: Optional profile name
            template_name: Optional template name
            
        Returns:
            The refined, ready-to-use prompt
        """
        result = self.compile(
            prompt,
            profile_name=profile_name,
            template_name=template_name
        )
        return result.refined_prompt
    
    def get_analysis_only(self, prompt: str, profile_name: Optional[str] = None) -> PromptAnalysis:
        """
        Get just the analysis without full compilation.
        
        Useful for previewing analysis before deciding to refine.
        """
        return self.analyzer.analyze(prompt, profile_name)
    
    def _auto_apply_recommendations(self, prompt: str, analysis: PromptAnalysis) -> str:
        """
        Automatically apply simple recommendation fixes to the prompt.
        
        Currently handles:
        - Adding missing context
        - Clarifying ambiguous terms
        """
        modified_prompt = prompt
        
        # Add context if missing
        if "Context" in analysis.missing:
            # Prepend context prompt
            modified_prompt = f"Provide background context: {modified_prompt}"
        
        # Clarify high-severity smells
        for smell in analysis.smells:
            if smell.severity == "high":
                # Add clarification as a separate sentence
                modified_prompt = f"{modified_prompt} {smell.suggestion}"
        
        return modified_prompt
    
    def _calculate_compilation_score(
        self,
        analysis: PromptAnalysis,
        was_refined: bool
    ) -> int:
        """
        Calculate overall compilation score from 0-100.
        
        This considers:
        - Analysis score (60% weight)
        - Whether refinement was applied (20% weight)
        - Number of recommendations (20% weight)
        """
        base_score = analysis.score * 0.6
        refinement_bonus = 20 if was_refined else 0
        recommendation_penalty = min(len(analysis.recommendations) * 2, 20)
        
        score = base_score + refinement_bonus - recommendation_penalty
        return max(0, min(100, int(score)))


def compile_prompt(
    prompt: str,
    refiner: PromptRefiner,
    profile_name: Optional[str] = None,
    template_name: Optional[str] = None,
) -> IntentCompilationResult:
    """
    Convenience function to compile a prompt using a global IntentCompiler instance.
    
    This creates a new IntentCompiler for each call, suitable for
    simple use cases or scripting.
    """
    compiler = IntentCompiler(refiner)
    return compiler.compile(
        prompt,
        profile_name=profile_name,
        template_name=template_name
    )
