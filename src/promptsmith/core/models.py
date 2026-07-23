"""
Core models for PromptSmith-cli.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _apply_rules(prompt: str, profile: Dict[str, Any]) -> str:
    """Apply deterministic prompt-improvement rules guided by a profile dict."""
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


def _ensure_content_completeness(result: str, profile: Dict[str, Any]) -> str:
    """Guarantee a profile's required domain areas and constraints survive
    into already-generated *content* (as opposed to _apply_rules, which
    frames a raw *prompt* headed into a backend).

    Deliberately narrower than _apply_rules: it only appends domain terms
    and constraints that are genuinely missing (a no-op for content that
    already covers them). It never appends role/tone/format framing
    sentences like "Act as if I am {role}." or "Use a {tone} tone." -
    those are instructions you give a model before generation, and make no
    sense tacked onto the end of finished code or prose. Appending them
    there previously leaked raw profile/persona text into visible output.
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
