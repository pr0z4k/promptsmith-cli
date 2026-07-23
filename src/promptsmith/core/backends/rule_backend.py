"""Deterministic prompt-refinement backend."""

from typing import Optional

from . import ModelBackend
from ..models import _apply_rules
from ..profile import RefinementProfile


class RuleBasedBackend(ModelBackend):
    """Apply PromptSmith's deterministic refinement rules."""

    def refine(self, prompt: str, profile: RefinementProfile) -> Optional[str]:
        self.last_error = None
        return _apply_rules(prompt, profile)
