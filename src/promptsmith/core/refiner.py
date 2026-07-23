"""
Prompt refinement for PromptSmith-cli.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from .exceptions import BackendError, ProfileNotFoundError
from .plugins import BackendRegistry
from .backends.rule_based import RuleBasedBackend
from .models import _ensure_content_completeness

if TYPE_CHECKING:
    from .profiles import ProfileManager
    from .templates import TemplateManager

logger = logging.getLogger(__name__)

class PromptRefiner:
    """Refines a raw prompt using profile constraints and an optional template."""

    def __init__(
        self,
        profile_manager: "ProfileManager",
        template_manager: Optional["TemplateManager"] = None,
    ):
        self.profile_manager = profile_manager
        self.template_manager = template_manager
        self.last_warning: Optional[str] = None
        self.last_backend_used: Optional[str] = None
        self.last_model_used: Optional[str] = None

    def refine(
        self,
        prompt: str,
        profile_name: str = "general",
        template_name: Optional[str] = None,
    ) -> str:
        """Refine a prompt using template expansion, backend processing, and rule-based fallback."""
        # Reset per-call state so a warning from a previous (possibly
        # failed) refine can't linger and be misread as describing this
        # call - last_backend_used/last_model_used already get fresh
        # values unconditionally below; last_warning was the one field
        # only ever assigned on a failure path and never cleared on
        # success.
        self.last_warning = None
        try:
            profile: Dict[str, Any] = self.profile_manager.get_profile(profile_name)
        except ProfileNotFoundError:
            profile = self.profile_manager.get_config(profile_name)
            if not profile:
                raise ProfileNotFoundError(profile_name) from None
        if template_name and self.template_manager:
            try:
                template = self.template_manager.get_config(template_name)
                if template:
                    base = template.get("prompt", "")
                    if base:
                        placeholders = re.findall(r"\{(\w+)\}", base)
                        expanded = base
                        for ph in placeholders:
                            expanded = expanded.replace(f"{{{ph}}}", prompt, 1)
                        prompt = expanded
            except Exception as e:
                logger.warning(f"Template expansion failed: {e}")
        backend_name = profile.get("backend", "rule")
        backend_cls = BackendRegistry.get(backend_name)
        if backend_cls is None:
            logger.error(f"Unknown backend: {backend_name}")
            raise BackendError(f"Unknown backend: {backend_name}")
        instance = None
        try:
            instance = backend_cls()
        except (TypeError, AttributeError) as e:
            logger.warning(f"Backend {backend_name} requires arguments: {e}. Falling back to rule-based.")
            instance = None

        if instance is None:
            instance = RuleBasedBackend()

        try:
            result = instance.refine(prompt, profile)
        except Exception as e:
            logger.warning(f"Backend {backend_name} refinement failed: {e}")
            self.last_warning = f"Backend {backend_name} failed: {e}"
            result = None
        if result is None:
            if hasattr(instance, "last_error") and instance.last_error:
                self.last_warning = instance.last_error
                logger.warning(f"Backend error: {self.last_warning}")
            fallback = RuleBasedBackend()
            result = fallback.refine(prompt, profile)
            self.last_backend_used = "rule"
            self.last_model_used = None
            if result is None:
                logger.error("All refinement methods failed, returning original prompt")
                return prompt
        else:
            self.last_backend_used = "rule" if isinstance(instance, RuleBasedBackend) else backend_name
            model_path = getattr(instance, "model_path", None)
            self.last_model_used = model_path.name if (model_path and self.last_backend_used != "rule") else None

        # Safety net: guarantee the profile's required domain areas and
        # constraints survive into the final text, regardless of which
        # backend produced it - this is what protects against e.g. an LLM
        # polish pass silently dropping most of a profile's domain list.
        #
        # Uses _ensure_content_completeness rather than _apply_rules here:
        # _apply_rules also injects role/tone/format *framing* sentences
        # ("Act as if I am {role}.", "Use a {tone} tone.") that belong in a
        # prompt headed into a model, not appended after the model has
        # already produced finished content. HybridBackend already calls
        # _apply_rules() itself to build that input prompt, so by the time
        # `result` reaches here the framing has done its job; re-running the
        # full rule set against the generated output was leaking that raw
        # persona/instruction text into what the user sees.
        try:
            result = _ensure_content_completeness(result, profile)
        except Exception as e:
            logger.warning(f"Could not verify profile content completeness: {e}")

        return result
