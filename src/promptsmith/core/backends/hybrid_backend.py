"""
Hybrid refinement backend: rules first, then LLM polish.

Runs the deterministic rule-based pass first (guaranteeing every role/domain/
tone/constraint from the profile is present, verbatim), then asks the local
LLM to rewrite that already-complete text into clearer prose - rather than
asking the LLM to generate structured content from a bare one-liner, which
smaller models handle less reliably.

Falls back to the pure rule-based text if the LLM is unavailable, errors, or
produces something that looks clearly broken (empty, or drastically shorter
than what it was given - a sign of truncation or the model losing content).
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from . import ModelBackend
from .llm_backend import LLMBasedBackend
from ..models import _apply_rules

logger = logging.getLogger(__name__)


class HybridBackend(ModelBackend):
    """Rules -> LLM polish, with a guaranteed-safe fallback to rules alone."""

    # Below this fraction of the rule-based text's length, treat the LLM's
    # output as likely truncated/degenerate rather than a legitimate rewrite.
    # Deliberately generous: a good polish tightening a verbose, mechanically
    # bulleted constraint list into flowing prose can legitimately be much
    # shorter while being strictly better - this floor should only catch
    # clearly-broken/truncated responses, not good compression.
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
            polished = self._llm_backend.refine(rule_based_result, profile, polish_mode=True)
        except Exception as e:
            self.last_error = f"LLM polish failed, used rule-based result instead: {e}"
            logger.warning(self.last_error)
            return rule_based_result

        if polished is None:
            self.last_error = self._llm_backend.last_error or "LLM polish returned no result"
            logger.warning(f"Hybrid: LLM polish unavailable ({self.last_error}), using rule-based result")
            return rule_based_result

        if self._looks_degenerate(polished, rule_based_result):
            self.last_error = "LLM polish output looked incomplete, used rule-based result instead"
            logger.warning(self.last_error)
            return rule_based_result

        return polished

    def _looks_degenerate(self, polished: str, original: str) -> bool:
        """Cheap sanity check: did the LLM plausibly preserve the content,
        or does this look like truncation/failure?"""
        if not polished or len(polished.strip()) < 20:
            return True
        if len(polished) < len(original) * self.MIN_LENGTH_RATIO:
            return True
        return False
