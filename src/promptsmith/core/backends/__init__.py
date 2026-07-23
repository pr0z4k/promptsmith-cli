"""
Backend module for PromptSmith-cli.

This module provides the abstract base class for all refinement backends.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ModelBackend(ABC):
    """
    Abstract base class for prompt-refinement backends.
    
    All backends must implement the refine() method which takes a prompt
    and a profile, and returns a refined prompt or None if refinement fails.
    
    Backends can be:
    - Rule-based: Deterministic refinement using predefined rules
    - LLM-based: Uses a language model to refine prompts
    - Custom: Any other refinement strategy
    """

    @abstractmethod
    def refine(self, prompt: str, profile: Dict[str, Any]) -> Optional[str]:
        """
        Refine a prompt using the backend's strategy.
        
        Args:
            prompt: The original prompt to refine
            profile: The profile dictionary containing refinement context
            
        Returns:
            The refined prompt string, or None if refinement is not possible
        """
        pass