"""Hybrid refinement backend: deterministic rules followed by local LLM polish."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from . import ModelBackend
from .llm_backend import LLMBasedBackend
from ..models import _apply_rules

logger = logging.getLogger(__name__)


class HybridBackend(ModelBackend):
    """Rules -> LLM polish, with a guaranteed rule-based fallback."""

    MIN_LENGTH_RATIO = 0.25

    def __init__(self, model_path: Optional[Path] = None):
        self._llm_backend = LLMBasedBackend(model_path=model_path)
        self.last_error: Optional[str] = None

    @property
    def model_path(self) -> Optional[Path]:
        return self._llm_backend.model_path

    def refine(self, prompt: str, profile: Dict[str, Any]) -> Optional[str]:
        rule_based_result = _apply_rules(prompt, profile)

        try:
            polished = self._llm_backend.refine(
                rule_based_result,
                profile,
                polish_mode=True,
            )
        except Exception as exc:
            self.last_error = "LLM polish failed; the rule-based result was used"
            logger.warning("Hybrid LLM polish failed (%s); using rules", type(exc).__name__)
            return rule_based_result

        if polished is None:
            self.last_error = self._llm_backend.last_error or "LLM polish returned no result"
            logger.warning("Hybrid LLM polish unavailable; using rules")
            return rule_based_result

        if self._looks_degenerate(polished, rule_based_result):
            self.last_error = "LLM polish output looked incomplete; the rule-based result was used"
            logger.warning("Hybrid LLM polish looked incomplete; using rules")
            return rule_based_result

        self.last_error = None
        return polished

    def _looks_degenerate(self, polished: str, original: str) -> bool:
        if not polished or len(polished.strip()) < 20:
            return True
        return len(polished) < len(original) * self.MIN_LENGTH_RATIO

    def unload(self) -> None:
        self._llm_backend.unload()
