"""
Plugin system for PromptSmith-cli.
"""

import logging
from typing import Dict, List, Optional, Type

from ..backends import ModelBackend

logger = logging.getLogger(__name__)


class BackendRegistry:
    """Registry for backend plugins."""
    _backends: Dict[str, Type[ModelBackend]] = {}

    @classmethod
    def register(cls, name: str, backend_class: Type[ModelBackend]) -> None:
        if not isinstance(backend_class, type) or not issubclass(backend_class, ModelBackend):
            raise TypeError(f"{backend_class} is not a subclass of ModelBackend")
        cls._backends[name] = backend_class
        logger.debug(f"Registered backend: {name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[ModelBackend]]:
        return cls._backends.get(name)

    @classmethod
    def list_backends(cls) -> List[str]:
        return list(cls._backends.keys())

    @classmethod
    def unregister(cls, name: str) -> bool:
        if name in cls._backends:
            del cls._backends[name]
            logger.debug(f"Unregistered backend: {name}")
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        cls._backends.clear()
        logger.debug("Cleared all backends")

    @classmethod
    def create_instance(cls, name: str, **kwargs) -> Optional[ModelBackend]:
        backend_cls = cls.get(name)
        if backend_cls is None:
            logger.warning(f"Backend '{name}' not found")
            return None
        try:
            return backend_cls(**kwargs)
        except Exception as e:
            from ..exceptions import BackendError
            logger.error(f"Failed to instantiate backend '{name}': {e}")
            raise BackendError(f"Failed to instantiate backend '{name}': {e}") from e