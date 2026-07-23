"""
PromptSmith-cli Core Module.

This module contains the core functionality for prompt refinement, including:
- Configuration management
- Profile and template management
- Backend plugins for refinement
- Prompt refinement orchestrator
"""

from .config import ConfigManager
from .config_store import YAMLConfigStore
from .exceptions import (
    BackendError,
    ProfileNotFoundError,
    PromptSmithError,
    TemplateNotFoundError,
    ValidationError,
)
from .profiles import ProfileManager
from .refiner import PromptRefiner
from .schemas import ProfileSchema, TemplateSchema, validate_profile, validate_template
from .templates import TemplateManager

# Import and register backends
from .backends import ModelBackend
from .backends.rule_based import RuleBasedBackend
from .backends.llm_backend import LLMBasedBackend
from .plugins import BackendRegistry

# Backwards-compatible aliases (previously imported from .models)
BaseModelBackend = ModelBackend
RuleBasedBackendClass = RuleBasedBackend

# Register default backends
try:
    BackendRegistry.register("rule", RuleBasedBackendClass)
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to register rule backend: {e}")

try:
    BackendRegistry.register("llm", LLMBasedBackend)
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to register llm backend: {e}")

try:
    from .backends.hybrid_backend import HybridBackend
    BackendRegistry.register("hybrid", HybridBackend)
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to register hybrid backend: {e}")

__all__ = [
    "ProfileManager",
    "TemplateManager",
    "ConfigManager",
    "YAMLConfigStore",
    "ModelBackend",
    "BaseModelBackend",
    "RuleBasedBackend",
    "RuleBasedBackendClass",
    "LLMBasedBackend",
    "PromptRefiner",
    "ProfileSchema",
    "TemplateSchema",
    "validate_profile",
    "validate_template",
    "PromptSmithError",
    "BackendError",
    "ProfileNotFoundError",
    "TemplateNotFoundError",
    "ValidationError",
    "BackendRegistry",
]