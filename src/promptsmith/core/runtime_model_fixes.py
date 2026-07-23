"""Runtime safeguards for local model selection and output cleanup."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from promptsmith.core.backends.llm_backend import LLMBasedBackend


def _same_path(left: Optional[Path], right: Optional[Path]) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def configure_runtime_model_behavior() -> None:
    """Make cached backends follow Settings and retain usable model output."""

    original_refine = LLMBasedBackend.refine
    if getattr(original_refine, "_promptsmith_runtime_fixed", False):
        return

    original_strip = LLMBasedBackend._strip_think_blocks

    def safe_strip_think_blocks(text: str) -> str:
        if not text:
            return text

        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if "<think>" in cleaned and "</think>" not in cleaned:
            # Some small non-reasoning models emit a stray opening token. The
            # previous implementation discarded the entire answer, which made
            # a perfectly usable response look empty. Remove only the marker.
            cleaned = cleaned.replace("<think>", "").strip()
        return cleaned

    def refresh_aware_refine(self, prompt, profile, polish_mode=False):
        selected = self._discover_default_model()
        if not _same_path(self.model_path, selected):
            self.unload()
            self.model_path = selected
            self.last_error = None
        return original_refine(self, prompt, profile, polish_mode=polish_mode)

    safe_strip_think_blocks._promptsmith_runtime_fixed = True  # type: ignore[attr-defined]
    refresh_aware_refine._promptsmith_runtime_fixed = True  # type: ignore[attr-defined]
    LLMBasedBackend._strip_think_blocks = staticmethod(safe_strip_think_blocks)
    LLMBasedBackend.refine = refresh_aware_refine  # type: ignore[assignment]
