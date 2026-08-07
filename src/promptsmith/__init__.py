"""
PromptSmith-cli main package.

This package provides the core functionality for prompt refinement.
"""

from promptsmith._version import (
    DIST_NAME,
    PRODUCT_NAME,
    PROJECT_URL,
    SUPPORT_URL,
    __version__,
    display_version,
)
from promptsmith.core import (
    BackendRegistry,
    ConfigManager,
    LLMBasedBackend,
    ModelBackend,
    ProfileManager,
    ProfileSchema,
    PromptRefiner,
    RuleBasedBackend,
    TemplateManager,
    TemplateSchema,
    validate_profile,
    validate_template,
)
from promptsmith.core.exceptions import (
    BackendError,
    ConfigurationError,
    DependencyError,
    FilesystemError,
    ProfileNotFoundError,
    PromptSmithError,
    TemplateNotFoundError,
    ValidationError,
)

__all__ = [
    "DIST_NAME",
    "PRODUCT_NAME",
    "PROJECT_URL",
    "SUPPORT_URL",
    "BackendError",
    "BackendRegistry",
    "ConfigManager",
    "ConfigurationError",
    "DependencyError",
    "FilesystemError",
    "LLMBasedBackend",
    "ModelBackend",
    "ProfileManager",
    "ProfileNotFoundError",
    "ProfileSchema",
    "PromptRefiner",
    "PromptSmithError",
    "RuleBasedBackend",
    "TemplateManager",
    "TemplateNotFoundError",
    "TemplateSchema",
    "ValidationError",
    "__version__",
    "display_version",
    "validate_profile",
    "validate_template",
]
