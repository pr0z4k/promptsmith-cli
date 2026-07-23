"""Prompt refinement orchestration for PromptSmith-cli."""

from __future__ import annotations

import logging
import re
import threading
from typing import TYPE_CHECKING, Dict, Optional

from .backends import ModelBackend, RefinementProfile
from .backends.rule_based import RuleBasedBackend
from .exceptions import BackendError, ProfileNotFoundError
from .models import _ensure_content_completeness
from .plugins import BackendRegistry

if TYPE_CHECKING:
    from .profiles import ProfileManager
    from .templates import TemplateManager

logger = logging.getLogger(__name__)


class PromptRefiner:
    """Coordinate profile lookup, template expansion, and backend execution.

    Backend instances are owned by the refiner and reused across calls. This is
    especially important for local LLM backends, where constructing an instance
    can load a multi-gigabyte native model. Call :meth:`unload` when the refiner
    is no longer needed.
    """

    def __init__(
        self,
        profile_manager: "ProfileManager",
        template_manager: Optional["TemplateManager"] = None,
    ) -> None:
        self.profile_manager = profile_manager
        self.template_manager = template_manager
        self.last_warning: Optional[str] = None
        self.last_backend_used: Optional[str] = None
        self.last_model_used: Optional[str] = None
        self._instances: Dict[str, ModelBackend] = {}
        self._lock = threading.RLock()

    def _load_profile(self, profile_name: str) -> RefinementProfile:
        try:
            return self.profile_manager.get_profile(profile_name)
        except ProfileNotFoundError:
            profile = self.profile_manager.get_config(profile_name)
            if not profile:
                raise ProfileNotFoundError(profile_name) from None
            return profile

    def _expand_template(self, prompt: str, template_name: Optional[str]) -> str:
        if not template_name or self.template_manager is None:
            return prompt

        try:
            template = self.template_manager.get_config(template_name)
        except Exception as exc:
            logger.warning("Template lookup failed (%s)", type(exc).__name__)
            self.last_warning = "The selected template could not be loaded"
            return prompt

        if not template:
            return prompt

        base = template.get("prompt", "")
        if not base:
            return prompt

        expanded = base
        for placeholder in re.findall(r"\{(\w+)\}", base):
            expanded = expanded.replace(f"{{{placeholder}}}", prompt, 1)
        return expanded

    def _get_backend(self, backend_name: str) -> ModelBackend:
        with self._lock:
            cached = self._instances.get(backend_name)
            if cached is not None:
                return cached

            try:
                instance = BackendRegistry.create_instance(backend_name)
            except (BackendError, ValueError) as exc:
                logger.warning(
                    "Backend '%s' construction failed (%s)",
                    backend_name,
                    type(exc).__name__,
                )
                raise BackendError(f"Backend '{backend_name}' is unavailable") from exc

            if instance is None:
                raise BackendError(f"Unknown backend: {backend_name}")

            self._instances[backend_name] = instance
            return instance

    def _rule_fallback(self) -> RuleBasedBackend:
        with self._lock:
            cached = self._instances.get("rule")
            if isinstance(cached, RuleBasedBackend):
                return cached

            instance = RuleBasedBackend()
            self._instances["rule"] = instance
            return instance

    def refine(
        self,
        prompt: str,
        profile_name: str = "general",
        template_name: Optional[str] = None,
    ) -> str:
        """Refine a prompt using template expansion and configured backend fallback."""

        self.last_warning = None
        profile = self._load_profile(profile_name)
        prompt = self._expand_template(prompt, template_name)
        backend_name = profile.get("backend", "rule")

        try:
            instance = self._get_backend(backend_name)
        except BackendError as exc:
            self.last_warning = str(exc)
            logger.warning("Configured backend unavailable; using deterministic rules")
            instance = self._rule_fallback()
            backend_name = "rule"

        try:
            result = instance.refine(prompt, profile)
        except Exception as exc:
            logger.warning(
                "Backend '%s' refinement failed (%s)",
                backend_name,
                type(exc).__name__,
            )
            self.last_warning = f"Backend '{backend_name}' failed; deterministic rules were used"
            result = None

        if result is None:
            backend_error = instance.last_error
            if backend_error:
                self.last_warning = backend_error
                logger.warning("Backend '%s' returned no result", backend_name)

            fallback = self._rule_fallback()
            result = fallback.refine(prompt, profile)
            self.last_backend_used = "rule"
            self.last_model_used = None
            if result is None:
                logger.error("All refinement methods failed; returning original prompt")
                return prompt
        else:
            self.last_backend_used = "rule" if isinstance(instance, RuleBasedBackend) else backend_name
            model_path = getattr(instance, "model_path", None)
            self.last_model_used = (
                model_path.name if model_path and self.last_backend_used != "rule" else None
            )

        try:
            return _ensure_content_completeness(result, profile)
        except Exception as exc:
            logger.warning(
                "Could not verify profile content completeness (%s)",
                type(exc).__name__,
            )
            return result

    def unload(self) -> None:
        """Release every backend owned by this refiner exactly once."""

        with self._lock:
            instances = list(self._instances.values())
            self._instances.clear()

        seen: set[int] = set()
        for instance in instances:
            identity = id(instance)
            if identity in seen:
                continue
            seen.add(identity)
            try:
                instance.unload()
            except Exception as exc:
                logger.warning(
                    "Backend cleanup failed (%s)",
                    type(exc).__name__,
                )

    def __del__(self) -> None:
        try:
            self.unload()
        except Exception:
            pass
