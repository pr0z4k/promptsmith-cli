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
    ConfigManager,
    ProfileManager,
    TemplateManager,
    PromptRefiner,
    ModelBackend,
    RuleBasedBackend,
    LLMBasedBackend,
    ProfileSchema,
    TemplateSchema,
    validate_profile,
    validate_template,
    BackendRegistry,
)

from promptsmith.core.exceptions import (
    PromptSmithError,
    BackendError,
    ConfigurationError,
    ProfileNotFoundError,
    TemplateNotFoundError,
    ValidationError,
    FilesystemError,
    DependencyError,
)

__all__ = [
    "__version__",
    "display_version",
    "DIST_NAME",
    "PRODUCT_NAME",
    "PROJECT_URL",
    "SUPPORT_URL",
    "ConfigManager",
    "ProfileManager",
    "TemplateManager",
    "PromptRefiner",
    "ModelBackend",
    "RuleBasedBackend",
    "LLMBasedBackend",
    "ProfileSchema",
    "TemplateSchema",
    "validate_profile",
    "validate_template",
    "BackendRegistry",
    "PromptSmithError",
    "BackendError",
    "ConfigurationError",
    "ProfileNotFoundError",
    "TemplateNotFoundError",
    "ValidationError",
    "FilesystemError",
    "DependencyError",
]