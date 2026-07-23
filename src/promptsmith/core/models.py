"""Core deterministic refinement helpers for PromptSmith-cli."""

import logging
from typing import List, Optional

from .profile import RefinementProfile

logger = logging.getLogger(__name__)


def _apply_rules(prompt: str, profile: RefinementProfile) -> str:
    """Apply deterministic prompt-improvement rules guided by a profile."""
    if not prompt:
        return prompt
    if not profile:
        logger.warning("_apply_rules called with empty profile")
        return prompt
    parts = [prompt]
    lower = prompt.lower()
    role = profile.get("role", "a general user")
    if role and "as a" not in lower and "like i'm" not in lower and role.lower() not in lower:
        parts.append(f"Act as if I am {role}.")
    domain: Optional[List[str]] = profile.get("domain", [])
    if domain:
        missing_domain = [d for d in domain if d.lower() not in lower]
        if missing_domain:
            parts.append(f"Focus on {', '.join(missing_domain)}.")
    tone = profile.get("tone", "neutral")
    if tone and tone.lower() not in lower:
        parts.append(f"Use a {tone} tone.")
    fmt = profile.get("format", "clear and concise text")
    if fmt and fmt.lower() not in lower:
        parts.append(f"Format the response as {fmt}.")
    constraints: Optional[List[str]] = profile.get("constraints", [])
    if constraints:
        for constraint in constraints:
            if constraint and constraint.lower() not in lower:
                parts.append(constraint)
    if len(prompt.split()) < 10:
        parts[0] = f"Please {prompt}"
    return " ".join(parts)


def _ensure_content_completeness(result: str, profile: RefinementProfile) -> str:
    """Preserve required profile content in an already-generated result.

    This is deliberately narrower than ``_apply_rules``: it only appends missing
    domain terms and constraints. Role, tone, and output-format instructions belong
    before generation and must not leak into finished content.
    """
    if not result or not profile:
        return result
    lower = result.lower()
    additions: List[str] = []

    domain: Optional[List[str]] = profile.get("domain", [])
    if domain:
        missing_domain = [d for d in domain if d.lower() not in lower]
        if missing_domain:
            additions.append(f"(Also covers: {', '.join(missing_domain)}.)")

    constraints: Optional[List[str]] = profile.get("constraints", [])
    if constraints:
        for constraint in constraints:
            if constraint and constraint.lower() not in lower:
                additions.append(constraint)

    if not additions:
        return result
    return " ".join([result, *additions])
