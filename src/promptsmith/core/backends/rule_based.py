"""
Rule-based refinement backend.
"""

import logging
from typing import Any, Dict, Optional

from ..backends import ModelBackend
from ..models import _apply_rules

logger = logging.getLogger(__name__)


class RuleBasedBackend(ModelBackend):
    """Deterministic rule-based refinement - no LLM required."""

    def refine(self, prompt: str, profile: Dict[str, Any]) -> Optional[str]:
        if not prompt:
            logger.warning("Empty prompt received")
            return None
        if not profile:
            logger.warning("Empty profile received; returning prompt unmodified")
            return prompt
        try:
            result = _apply_rules(prompt, profile)
            logger.debug("Rule-based refinement applied")
            return result if result else prompt
        except Exception as exc:
            logger.error(f"Rule-based refinement failed: {exc}")
            from ..exceptions import BackendError
            raise BackendError(f"Rule-based refinement failed: {exc}") from exc