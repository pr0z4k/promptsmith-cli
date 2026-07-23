"""Shared contracts for prompt-refinement backends."""

from abc import ABC, abstractmethod
from typing import Optional

from ..profile import RefinementProfile


class ModelBackend(ABC):
    """Stable interface implemented by every refinement backend."""

    last_error: Optional[str] = None

    @abstractmethod
    def refine(self, prompt: str, profile: RefinementProfile) -> Optional[str]:
        """Return a refined prompt, or ``None`` when refinement is unavailable."""

    def unload(self) -> None:
        """Release backend resources.

        Stateless backends require no cleanup, so the default implementation is
        intentionally a no-op. Resource-owning backends may override it.
        """
