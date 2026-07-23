"""Backend registry for PromptSmith-cli.

The registry is deliberately in-process only. PromptSmith does not discover or
import arbitrary modules from user-controlled paths, configuration files, or
Python packaging entry points. Backends must be imported by trusted application
code and registered explicitly.
"""

from __future__ import annotations

import logging
import re
import threading
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Type

from ..backends import ModelBackend

logger = logging.getLogger(__name__)

_BACKEND_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class BackendRegistry:
    """Thread-safe registry for explicitly imported backend classes.

    Registration names are stable identifiers used by configuration and UI
    code. Duplicate registration is rejected by default so an import-order
    change cannot silently replace a trusted backend implementation.
    """

    _backends: Dict[str, Type[ModelBackend]] = {}
    _lock = threading.RLock()

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str) or not _BACKEND_NAME_RE.fullmatch(name):
            raise ValueError(
                "Backend name must start with a lowercase letter and contain "
                "only lowercase letters, numbers, '_' or '-' (maximum 64 characters)"
            )
        return name

    @classmethod
    def register(
        cls,
        name: str,
        backend_class: Type[ModelBackend],
        *,
        replace: bool = False,
    ) -> None:
        """Register a trusted backend class.

        ``replace`` exists for controlled application/test reconfiguration. It
        must be requested explicitly; normal registration never overwrites an
        existing backend silently.
        """

        name = cls._validate_name(name)
        if not isinstance(backend_class, type) or not issubclass(backend_class, ModelBackend):
            raise TypeError(f"{backend_class!r} is not a subclass of ModelBackend")

        with cls._lock:
            existing = cls._backends.get(name)
            if existing is not None and existing is not backend_class and not replace:
                raise ValueError(f"Backend '{name}' is already registered")
            cls._backends[name] = backend_class
        logger.debug("Registered backend: %s", name)

    @classmethod
    def get(cls, name: str) -> Optional[Type[ModelBackend]]:
        name = cls._validate_name(name)
        with cls._lock:
            return cls._backends.get(name)

    @classmethod
    def list_backends(cls) -> List[str]:
        with cls._lock:
            return sorted(cls._backends)

    @classmethod
    def snapshot(cls) -> Mapping[str, Type[ModelBackend]]:
        """Return an immutable point-in-time view of registered backends."""

        with cls._lock:
            return MappingProxyType(dict(cls._backends))

    @classmethod
    def unregister(cls, name: str) -> bool:
        name = cls._validate_name(name)
        with cls._lock:
            removed = cls._backends.pop(name, None)
        if removed is not None:
            logger.debug("Unregistered backend: %s", name)
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._backends.clear()
        logger.debug("Cleared all backends")

    @classmethod
    def create_instance(cls, name: str, **kwargs) -> Optional[ModelBackend]:
        name = cls._validate_name(name)
        backend_cls = cls.get(name)
        if backend_cls is None:
            logger.warning("Backend '%s' not found", name)
            return None
        try:
            return backend_cls(**kwargs)
        except Exception as exc:
            from ..exceptions import BackendError

            logger.error("Failed to instantiate backend '%s': %s", name, exc)
            raise BackendError(f"Failed to instantiate backend '{name}'") from exc
