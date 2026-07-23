"""
Prompt analysis for PromptSmith-cli.

Provides deterministic analysis of prompts including:
- Readiness scoring
- Type detection (coding, architecture, documentation, etc.)
- Missing elements detection
- Smell detection with explanations
- Profile recommendations
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re


@dataclass
class PromptSmell:
    """Represents a detected issue in a prompt."""
    term: str
    explanation: str
    severity: str  # "low", "medium", "high"
    suggestion: str


@dataclass
class PromptRecommendation:
    """Actionable recommendation for improving a prompt."""
    category: str  # "missing", "clarity", "specificity", "structure"
    description: str
    action: str
    priority: int  # 1-5, higher is more important


@dataclass
class PromptChallenge:
    """A clarifying question surfacing a gap or ambiguity in the prompt.

    Distinct from PromptSmell (which flags a single ambiguous word) and
    PromptRecommendation (which suggests a fix): a Challenge asks the user
    a real question about intent that no amount of mechanical rewriting can
    answer on its own - deliberately deterministic/rule-based rather than
    LLM-generated, since generating a genuinely useful clarifying question
    is a harder reasoning task than rewriting a prompt, and small local
    models are not reliable at it. Informational only - never blocks
    Refine, applies identically regardless of profile, template, or backend.
    """
    question: str
    reason: str
    category: str  # "scope", "success_criteria", "audience", "quantity", "integration"


@dataclass
class PromptAnalysis:
    """Complete analysis of a prompt's quality and readiness."""
    score: int
    detected_type: str
    missing: List[str] = field(default_factory=list)
    smells: List[PromptSmell] = field(default_factory=list)
    recommendations: List[PromptRecommendation] = field(default_factory=list)
    challenges: List[PromptChallenge] = field(default_factory=list)
    recommended_profile: str = "General"
    is_ready: bool = False
    readiness_reason: str = ""
    
    def get_readiness_percentage(self) -> int:
        """Returns the readiness as a percentage (0-100)."""
        return min(100, max(0, self.score))
    
    def get_summary(self) -> str:
        """Returns a human-readable summary of the analysis."""
        lines = []
        lines.append(f"Readiness: {self.get_readiness_percentage()}%")
        lines.append(f"Type: {self.detected_type}")
        lines.append(f"Profile: {self.recommended_profile}")
        
        if self.missing:
            lines.append(f"Missing: {', '.join(self.missing)}")
        if self.smells:
            lines.append(f"Smells: {len(self.smells)} detected")
        if self.recommendations:
            lines.append(f"Recommendations: {len(self.recommendations)}")
        if self.challenges:
            lines.append(f"Challenges: {len(self.challenges)}")
        
        return " | ".join(lines)


class PromptAnalyzer:
    """
    Analyzes prompts for quality, completeness, and readiness.
    
    This is a deterministic analyzer that does not require an LLM.
    All analysis is offline, instant, and repeatable.
    """
    
    # Type detection patterns mapped to types and recommended profiles
    TYPE_PATTERNS: Dict[str, Tuple[List[str], str, str]] = {
        "aem": ([
            "aem", "adobe experience manager", "adobe experience",
            "sling", "osgi", "jcr", "cq", "crx", "felix",
            "aem component", "aem template", "aem page",
            "experience manager", "content package", "sling model"
        ], "aem", "AEM Developer"),
        
        "nextjs": ([
            "nextjs", "next js", "next.js", "app router", "pages router",
            "server component", "client component", "next/config",
            "getserversideprops", "getstaticprops", "middleware",
            "next image", "next link", "next font"
        ], "nextjs", "NextJS Developer"),
        
        "react": ([
            "react", "jsx", "tsx", "hooks", "usestate", "useeffect", "reducer",
            "functional component", "class component",
            "react props", "react state", "react hooks", "react router"
        ], "react", "React Developer"),
        
        "react-aem": ([
            "react", "aem", "spa editor", "react aem",
            "aem react", "spa", "single page application"
        ], "react-aem", "React AEM Developer"),
        
        "nextjs-aem": ([
            "nextjs", "aem", "nextjs aem", "aem nextjs",
            "headless", "graphql", "content fragment"
        ], "nextjs-aem", "NextJS AEM Developer"),
        
        "customer-portal": ([
            "customer portal", "portal", "adobe experience",
            "web experience", "digital experience"
        ], "customer-portal", "Customer Portal Architect"),
        
        "coding": ([
            "python", "java", "javascript", "typescript", "code", 
            "endpoint",
            "bug", "refactor", "algorithm", "data structure",
            "implement", "write code", "develop", "program"
        ], "coding", "Vibe Coding"),
        
        "architecture": ([
            "architecture", "system design",
            "diagram", "microservice", "monolith",
            "scalability", "tradeoff", "trade-off",
            "high-level", "low-level", "blueprint"
        ], "architecture", "Solution Architect"),
        
        "documentation": ([
            "documentation", "write docs", "readme", "markdown",
            "api docs", "user guide", "tutorial",
            "explainer"
        ], "documentation", "Technical Writer"),
        
        "email": ([
            "email", "letter", "write to", "respond to",
            "compose", "draft", "subject line"
        ], "email", "General"),
        
        "executive": ([
            "executive", "strategy", "business case", "roadmap",
            "prioritization", "roi", "stakeholder"
        ], "executive", "Executive"),
        
        "planning": ([
            "plan", "planning", "timeline", "milestone", "deliverable",
            "sprint", "agile", "scrum", "kanban"
        ], "planning", "Project Manager"),
        
        "research": ([
            "research", "investigate", "compare", "evaluate",
            "analysis", "look into", "explore"
        ], "research", "Research Analyst"),
    }
    
    # Ambiguous terms that need clarification
    AMBIGUOUS_TERMS: Dict[str, Tuple[str, str, str]] = {
        "modern": (
            "What does 'modern' mean?",
            "medium",
            "Specify the timeframe, version, or technological context"
        ),
        "best": (
            "Define criteria for 'best'",
            "high",
            "Specify what metrics or qualities make something 'best'"
        ),
        "optimize": (
            "Optimize for what?",
            "high",
            "Specify: performance, memory, readability, maintainability, or cost"
        ),
        "simple": (
            "Define simplicity criteria",
            "medium",
            "Specify what aspects should be simplified and to what degree"
        ),
        "fast": (
            "How fast?",
            "medium",
            "Specify performance requirements or benchmarks"
        ),
        "good": (
            "Define quality metrics",
            "medium",
            "Specify what makes a solution 'good' in this context"
        ),
        "better": (
            "Better than what?",
            "high",
            "Define the baseline or comparison point"
        ),
        "easy": (
            "Easy for whom?",
            "medium",
            "Specify the target audience and their skill level"
        ),
        "complex": (
            "Define complexity scope",
            "medium",
            "Specify what aspects are complex and why"
        ),
        "beautiful": (
            "Define aesthetic criteria",
            "low",
            "Specify design principles or style preferences"
        ),
    }
    
    # Required elements for a complete prompt
    REQUIRED_ELEMENTS: List[Tuple[str, List[str], str]] = [
        ("Context", ["background", "context", "situation", "problem", "goal"], 
         "Add background information about the task or problem"),
        ("Audience/Role", ["as a", "as if i am", "like i'm", "for a", "target audience"],
         "Specify who the output is for or what role to assume"),
        ("Output Format", ["output", "format", "return", "in the form of"],
         "Specify the desired format (text, code, list, table, etc.)"),
        ("Constraints", ["must", "should", "must not", "avoid", "requirement", "constraint"],
         "Add constraints or requirements that must be met"),
        ("Purpose", ["why", "so that", "in order to", "purpose", "goal"],
         "Clarify the purpose or intended use of the output"),
    ]
    
    # Minimum word counts for different prompt types
    MIN_WORD_COUNTS: Dict[str, int] = {
        "general": 10,
        "coding": 15,
        "architecture": 20,
        "documentation": 20,
        "email": 10,
        "aem": 15,
        "nextjs": 15,
        "react": 15,
        "customer-portal": 20,
    }
    
    # Profile preferences for each type
    TYPE_PROFILE_MAP: Dict[str, str] = {
        "aem": "AEM Developer",
        "nextjs": "NextJS Developer",
        "react": "React Developer",
        "react-aem": "React AEM Developer",
        "nextjs-aem": "NextJS AEM Developer",
        "customer-portal": "Customer Portal Architect",
        "coding": "Vibe Coding",
        "architecture": "Solution Architect",
        "documentation": "Technical Writer",
        "email": "General",
        "executive": "Executive",
        "planning": "Project Manager",
        "research": "Research Analyst",
    }
    
    def __init__(self):
        """Initialize the analyzer."""
        pass
    
    def analyze(self, prompt: str, current_profile: Optional[str] = None) -> PromptAnalysis:
        """
        Analyze a prompt and return a complete analysis.
        
        Args:
            prompt: The prompt text to analyze
            current_profile: Optional current profile for context
            
        Returns:
            PromptAnalysis with all analysis results
        """
        if not prompt or not prompt.strip():
            return PromptAnalysis(
                score=0,
                detected_type="empty",
                missing=["Prompt is empty"],
                recommended_profile="General",
                is_ready=False,
                readiness_reason="Prompt is empty"
            )
        
        prompt_lower = prompt.lower()
        words = prompt.split()
        word_count = len(words)
        
        # Detect type
        detected_type, confidence = self._detect_type(prompt_lower)
        
        # Check missing elements
        missing = self._check_missing_elements(prompt_lower)
        
        # Detect smells
        smells = self._detect_smells(prompt_lower)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            prompt_lower, detected_type, missing, smells, word_count
        )
        
        # Generate challenges (deterministic clarifying questions - informational only)
        challenges = self._generate_challenges(prompt, prompt_lower)

        # Determine recommended profile
        recommended_profile = self._recommend_profile(detected_type, current_profile)
        
        # Calculate score
        score = self._calculate_score(
            word_count, missing, smells, detected_type, recommendations
        )
        
        # Determine readiness
        is_ready, readiness_reason = self._assess_readiness(
            score, missing, smells, word_count, detected_type
        )
        
        return PromptAnalysis(
            score=score,
            detected_type=detected_type,
            missing=missing,
            smells=smells,
            recommendations=recommendations,
            challenges=challenges,
            recommended_profile=recommended_profile,
            is_ready=is_ready,
            readiness_reason=readiness_reason
        )
    
    # Combined-technology types and the two single-technology types whose
    # independent presence should make the combined type win, even when
    # its own raw pattern-weight sum is lower. Without this, a prompt that
    # mentions both technologies but doesn't happen to phrase them as one
    # of the explicit multi-word compound patterns (e.g. "AEM component
    # using GraphQL... in Next.js" rather than "nextjs aem") gets
    # classified as whichever single type happened to match a longer
    # phrase (e.g. "aem component"), even though both technologies are
    # clearly present.
    _COMBINED_TYPE_PARENTS: Dict[str, Tuple[str, str]] = {
        "react-aem": ("react", "aem"),
        "nextjs-aem": ("nextjs", "aem"),
    }

    def _detect_type(self, prompt: str) -> Tuple[str, float]:
        """
        Detect the type of prompt from its content.
        
        Uses a weighted scoring system that prioritizes:
        1. Longer, more specific patterns
        2. Exact phrase matches
        3. Multiple pattern matches within same type
        
        Returns:
            Tuple of (detected_type, confidence_score)
        """
        # Collect all matches with their weights
        matches = []  # (type_name, pattern, pattern_length)
        
        for type_name, (patterns, _, _) in self.TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(rf"\b{re.escape(pattern)}\b", prompt):
                    # Longer patterns get higher weight
                    weight = len(pattern.split())
                    matches.append((type_name, pattern, weight))
        
        if not matches:
            return "general", 0.0
        
        # Group by type and sum weights
        type_scores = {}
        for type_name, _pattern, weight in matches:
            type_scores[type_name] = type_scores.get(type_name, 0) + weight

        # Prefer a combined type over either single parent type when both
        # parents have independent signal, regardless of raw weight sums.
        # Boosts strictly above the higher parent's score (not just equal
        # to it) - an equal score still loses ties to whichever type
        # happens to be inserted first in type_scores (dict iteration
        # order follows TYPE_PATTERNS' definition order, where the single
        # types are defined before the combined ones).
        for combined_type, (parent_a, parent_b) in self._COMBINED_TYPE_PARENTS.items():
            if type_scores.get(parent_a, 0) > 0 and type_scores.get(parent_b, 0) > 0:
                parent_score = max(type_scores.get(parent_a, 0), type_scores.get(parent_b, 0))
                if type_scores.get(combined_type, 0) <= parent_score:
                    type_scores[combined_type] = parent_score + 1

        # Get best match
        best_type = max(type_scores.items(), key=lambda x: x[1])
        
        # Normalize confidence to 0-1 range
        max_possible = max(len(p.split()) for _, (patterns, _, _) in self.TYPE_PATTERNS.items() for p in patterns)
        confidence = min(1.0, best_type[1] / max_possible) if max_possible > 0 else 0.0
        
        # If confidence is low, fall back to general
        if best_type[1] < 1:
            return "general", confidence
        
        return best_type[0], confidence
    
    def _check_missing_elements(self, prompt: str) -> List[str]:
        """Check which required elements are missing from the prompt."""
        missing = []
        prompt_lower = prompt.lower()
        
        for element_name, keywords, _ in self.REQUIRED_ELEMENTS:
            found = any(keyword in prompt_lower for keyword in keywords)
            if not found:
                missing.append(element_name)
        
        return missing
    
    def _detect_smells(self, prompt: str) -> List[PromptSmell]:
        """Detect code smells (ambiguous or problematic terms) in the prompt."""
        smells = []
        prompt_lower = prompt.lower()
        
        for term, (explanation, severity, suggestion) in self.AMBIGUOUS_TERMS.items():
            # Use word boundaries to avoid partial matches
            if re.search(rf"\b{re.escape(term)}\b", prompt_lower):
                smells.append(PromptSmell(
                    term=term,
                    explanation=explanation,
                    severity=severity,
                    suggestion=suggestion
                ))
        
        return smells

    # Domain-agnostic ambiguity categories a real person would want clarified
    # before spending AI compute - deliberately not type-specific, so these
    # apply identically to a React component, an HR policy, or a business
    # case. Each category matches only whole words (word-boundary regex),
    # same discipline as type detection, to avoid substring false positives.
    _SCOPE_TERMS = ["reusable", "flexible", "generic", "configurable", "scalable", "extensible", "modular"]
    _SUCCESS_TERMS = ["done when", "success", "acceptance criteria", "definition of done",
                       "complete when", "test", "validate", "verify", "criteria"]
    _AUDIENCE_TERMS = ["for a", "for the", "used by", "audience", "consumer", "end user",
                        "reader", "customer", "team", "developer", "as a", "as if i am"]
    _QUANTITY_TERMS = ["some", "several", "many", "a few", "a couple", "multiple"]
    _INTEGRATION_TERMS = ["integrate", "add to", "extend", "existing", "update the", "modify the"]
    _CONSTRAINT_TERMS = ["version", "using", "built with", "based on", "framework",
                          "convention", "style guide", "pattern", "stack"]

    def _generate_challenges(self, prompt: str, prompt_lower: str) -> List[PromptChallenge]:
        """Generate deterministic clarifying questions about genuine gaps in
        the prompt. Informational only - never blocks Refine. Deliberately
        rule-based rather than LLM-generated: producing a genuinely useful
        clarifying question is a harder reasoning task than rewriting a
        prompt, and small local models are not reliable at it."""
        challenges: List[PromptChallenge] = []

        def has_any(terms: List[str]) -> Optional[str]:
            for t in terms:
                if re.search(rf"\b{re.escape(t)}\b", prompt_lower):
                    return t
            return None

        # 1. Vague scope/flexibility words without saying what varies
        scope_hit = has_any(self._SCOPE_TERMS)
        if scope_hit:
            challenges.append(PromptChallenge(
                question=(
                    f"What specifically should vary or be configurable? "
                    f"(You said {scope_hit!r}, but not what changes between uses.)"
                ),
                reason=f"'{scope_hit}' implies flexibility without specifying what actually varies.",
                category="scope",
            ))

        # 2. No definition of done / success criteria
        if not has_any(self._SUCCESS_TERMS):
            challenges.append(PromptChallenge(
                question="How will you know this is correct or complete?",
                reason="No success criteria, test, or definition of 'done' was mentioned.",
                category="success_criteria",
            ))

        # 3. No audience/consumer specified
        if not has_any(self._AUDIENCE_TERMS):
            challenges.append(PromptChallenge(
                question="Who or what will use or consume this?",
                reason="No audience, user, or consumer was mentioned.",
                category="audience",
            ))

        # 4. Ambiguous quantity without a specific number
        qty_hit = has_any(self._QUANTITY_TERMS)
        if qty_hit and not re.search(r"\d", prompt):
            challenges.append(PromptChallenge(
                question=f"Can you give an exact number instead of {qty_hit!r}?",
                reason="A vague quantity was used without a specific number.",
                category="quantity",
            ))

        # 5. Sounds like it's extending something existing, but that
        # existing system's constraints were never described
        if has_any(self._INTEGRATION_TERMS) and not has_any(self._CONSTRAINT_TERMS):
            challenges.append(PromptChallenge(
                question=(
                    "What does the existing system look like (framework, "
                    "conventions, version) that this needs to fit into?"
                ),
                reason=(
                    "This sounds like it extends or integrates with something "
                    "existing, but that system's constraints weren't described."
                ),
                category="integration",
            ))

        return challenges

    def _generate_recommendations(
        self, 
        prompt: str, 
        detected_type: str, 
        missing: List[str],
        smells: List[PromptSmell],
        word_count: int
    ) -> List[PromptRecommendation]:
        """Generate actionable recommendations for improving the prompt."""
        recommendations = []
        min_words = self.MIN_WORD_COUNTS.get(detected_type, 10)
        
        # Recommend adding missing elements
        priority = 5
        for element in missing:
            # Find the suggestion for this element
            suggestion = ""
            for elem_name, _, elem_suggestion in self.REQUIRED_ELEMENTS:
                if elem_name == element:
                    suggestion = elem_suggestion
                    break
            
            recommendations.append(PromptRecommendation(
                category="missing",
                description=f"Add {element}",
                action=suggestion,
                priority=priority
            ))
            priority -= 1
        
        # Recommend clarifying smells
        for smell in smells:
            if smell.severity == "high":
                priority = 5
            elif smell.severity == "medium":
                priority = 3
            else:
                priority = 1
            
            recommendations.append(PromptRecommendation(
                category="clarity",
                description=f"Clarify '{smell.term}'",
                action=smell.suggestion,
                priority=priority
            ))
        
        # Recommend expanding if too short
        if word_count < min_words:
            recommendations.append(PromptRecommendation(
                category="structure",
                description=f"Prompt is too short ({word_count} words)",
                action=f"Expand to at least {min_words} words with more context and details",
                priority=4
            ))
        
        # Type-specific recommendations
        type_recommendations = self._get_type_specific_recommendations(detected_type, prompt)
        recommendations.extend(type_recommendations)
        
        # Sort by priority
        recommendations.sort(key=lambda r: r.priority, reverse=True)
        
        return recommendations
    
    def _get_type_specific_recommendations(self, detected_type: str, prompt: str) -> List[PromptRecommendation]:
        """Generate type-specific recommendations."""
        recommendations = []
        prompt_lower = prompt.lower()
        
        if detected_type == "coding":
            if "test" not in prompt_lower and "tests" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="coding",
                    description="Consider adding tests",
                    action="Add requirements for unit tests or specify testing approach",
                    priority=3
                ))
            if "error" not in prompt_lower and "handle" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="coding",
                    description="Consider error handling",
                    action="Specify how errors should be handled",
                    priority=2
                ))
                
        elif detected_type == "aem":
            if "component" in prompt_lower and "path" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="aem",
                    description="Specify component path",
                    action="Add the JCR path where the component should be created",
                    priority=4
                ))
            if "best practice" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="aem",
                    description="Reference AEM best practices",
                    action="Mention adherence to AEM development best practices",
                    priority=3
                ))
                
        elif detected_type == "nextjs":
            if "type" not in prompt_lower and "typescript" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="nextjs",
                    description="Specify TypeScript vs JavaScript",
                    action="Clarify whether the code should be in TypeScript or JavaScript",
                    priority=3
                ))
                
        elif detected_type == "react":
            if "component" in prompt_lower and "props" not in prompt_lower:
                recommendations.append(PromptRecommendation(
                    category="react",
                    description="Define component props",
                    action="Specify the props interface or expected properties",
                    priority=3
                ))
        
        return recommendations
    
    def _recommend_profile(self, detected_type: str, current_profile: Optional[str]) -> str:
        """Recommend the best profile for this prompt type."""
        if current_profile and current_profile != "General":
            # If user has a current profile, prefer it
            return current_profile
        
        # Map detected type to recommended profile
        return self.TYPE_PROFILE_MAP.get(detected_type, "General")
    
    def _calculate_score(
        self,
        word_count: int,
        missing: List[str],
        smells: List[PromptSmell],
        detected_type: str,
        recommendations: List[PromptRecommendation]
    ) -> int:
        """
        Calculate a score from 0-100 based on prompt quality.
        
        Higher scores indicate better prompts that are ready for AI.
        """
        score = 100
        min_words = self.MIN_WORD_COUNTS.get(detected_type, 10)
        
        # Penalize for missing elements (up to 40 points)
        score -= len(missing) * 10
        
        # Penalize for smells (up to 30 points)
        high_smells = sum(1 for s in smells if s.severity == "high")
        medium_smells = sum(1 for s in smells if s.severity == "medium")
        score -= high_smells * 7
        score -= medium_smells * 3
        
        # Penalize for short prompts (up to 20 points)
        if word_count < min_words:
            deficit = min_words - word_count
            score -= min(deficit * 2, 20)
        
        # Bonus for having all required elements (up to 10 points)
        if not missing:
            score += 10
        
        # Bonus for no high-severity smells (up to 5 points)
        if high_smells == 0:
            score += 5
        
        return max(0, min(100, score))
    
    def _assess_readiness(
        self,
        score: int,
        missing: List[str],
        smells: List[PromptSmell],
        word_count: int,
        detected_type: str
    ) -> Tuple[bool, str]:
        """
        Assess whether the prompt is ready for AI inference.
        
        Returns:
            Tuple of (is_ready, reason)
        """
        min_words = self.MIN_WORD_COUNTS.get(detected_type, 10)
        
        # Ready if:
        # - Score >= 80
        # - No high-severity smells
        # - No critical missing elements
        # - Minimum word count met
        
        high_smells = sum(1 for s in smells if s.severity == "high")
        critical_missing = any(m in ["Context", "Audience/Role"] for m in missing)
        
        if score >= 80 and high_smells == 0 and not critical_missing and word_count >= min_words:
            return True, f"Ready for AI ({score}/100)"
        
        # Provide specific reasons
        reasons = []
        if score < 80:
            reasons.append(f"score too low ({score}/100)")
        if high_smells > 0:
            reasons.append(f"{high_smells} high-severity smell(s)")
        if critical_missing:
            reasons.append("missing critical elements")
        if word_count < min_words:
            reasons.append(f"too short ({word_count} < {min_words} words)")
        
        return False, f"Not ready: {', '.join(reasons)}"
