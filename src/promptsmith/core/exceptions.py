"""
Custom exceptions for PromptSmith-cli.
"""

from typing import Optional


class PromptSmithError(Exception):
    """Base exception class for all PromptSmith-cli errors."""
    pass


class BackendError(PromptSmithError):
    """Exception raised for backend-related errors."""
    pass


class ConfigurationError(PromptSmithError):
    """Exception raised for configuration-related errors."""
    pass


class ProfileNotFoundError(PromptSmithError):
    """Exception raised when a requested profile is not found."""
    def __init__(self, profile_name: str, message: Optional[str] = None):
        self.profile_name = profile_name
        message = message or f"Profile '{profile_name}' not found"
        super().__init__(message)


class TemplateNotFoundError(PromptSmithError):
    """Exception raised when a requested template is not found."""
    def __init__(self, template_name: str, message: Optional[str] = None):
        self.template_name = template_name
        message = message or f"Template '{template_name}' not found"
        super().__init__(message)


class ValidationError(PromptSmithError):
    """Exception raised when data validation fails."""
    def __init__(self, errors: list, message: Optional[str] = None):
        self.errors = errors
        message = message or f"Validation failed: {', '.join(errors)}"
        super().__init__(message)


class FilesystemError(PromptSmithError):
    """Exception raised for filesystem-related errors."""
    pass


class DependencyError(PromptSmithError):
    """Exception raised when a required dependency is missing."""
    def __init__(self, dependency: str, install_command: Optional[str] = None, message: Optional[str] = None):
        self.dependency = dependency
        self.install_command = install_command
        message = message or f"Missing dependency: {dependency}"
        if install_command:
            message += f"\nInstall with: {install_command}"
        super().__init__(message)