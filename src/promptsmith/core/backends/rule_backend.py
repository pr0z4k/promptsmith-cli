"""Deterministic prompt-refinement backend."""

import logging

from ..exceptions import BackendError
from ..models import _apply_rules
from ..profile import RefinementProfile
from . import ModelBackend

logger = logging.getLogger(__name__)


class RuleBasedBackend(ModelBackend):
    """Apply PromptSmith's deterministic refinement rules - no LLM required."""

    def refine(self, prompt: str, profile: RefinementProfile) -> str | None:
        self.last_error = None
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
            raise BackendError(f"Rule-based refinement failed: {exc}") from exc
