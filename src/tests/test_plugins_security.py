"""Security and robustness tests for the explicit backend registry."""

from types import MappingProxyType

import pytest

from promptsmith.core.backends import ModelBackend
from promptsmith.core.plugins import BackendRegistry


class BackendA(ModelBackend):
    def refine(self, prompt, profile):
        return prompt


class BackendB(ModelBackend):
    def refine(self, prompt, profile):
        return prompt.upper()


@pytest.fixture(autouse=True)
def isolated_registry():
    original = dict(BackendRegistry.snapshot())
    BackendRegistry.clear()
    yield
    BackendRegistry.clear()
    for name, backend in original.items():
        BackendRegistry.register(name, backend)


@pytest.mark.parametrize(
    "name",
    ["", "Upper", "../evil", "a/b", "a.b", " leading", "trailing ", "a" * 65],
)
def test_rejects_unsafe_or_unstable_backend_names(name):
    with pytest.raises(ValueError):
        BackendRegistry.register(name, BackendA)


def test_duplicate_registration_cannot_silently_replace_backend():
    BackendRegistry.register("safe", BackendA)

    with pytest.raises(ValueError, match="already registered"):
        BackendRegistry.register("safe", BackendB)

    assert BackendRegistry.get("safe") is BackendA


def test_explicit_replace_is_supported_for_controlled_reconfiguration():
    BackendRegistry.register("safe", BackendA)
    BackendRegistry.register("safe", BackendB, replace=True)

    assert BackendRegistry.get("safe") is BackendB


def test_snapshot_is_immutable_and_detached_from_registry():
    BackendRegistry.register("safe", BackendA)
    snapshot = BackendRegistry.snapshot()

    assert isinstance(snapshot, MappingProxyType)
    with pytest.raises(TypeError):
        snapshot["other"] = BackendB

    BackendRegistry.unregister("safe")
    assert snapshot["safe"] is BackendA
    assert BackendRegistry.get("safe") is None


def test_backend_list_is_deterministic():
    BackendRegistry.register("zeta", BackendA)
    BackendRegistry.register("alpha", BackendB)

    assert BackendRegistry.list_backends() == ["alpha", "zeta"]


def test_instantiation_error_does_not_expose_constructor_details():
    class FailingBackend(ModelBackend):
        def __init__(self):
            raise RuntimeError("secret constructor detail")

        def refine(self, prompt, profile):
            return None

    BackendRegistry.register("failing", FailingBackend)

    with pytest.raises(Exception) as exc_info:
        BackendRegistry.create_instance("failing")

    assert "secret constructor detail" not in str(exc_info.value)
