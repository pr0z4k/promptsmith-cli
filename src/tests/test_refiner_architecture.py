from __future__ import annotations

from typing import Optional

import pytest

from promptsmith.core.backends import ModelBackend, RefinementProfile
from promptsmith.core.plugins import BackendRegistry
from promptsmith.core.refiner import PromptRefiner


class StubProfileManager:
    def __init__(self, backend: str) -> None:
        self.backend = backend

    def get_profile(self, name: str) -> RefinementProfile:
        return {
            "name": name,
            "role": "Tester",
            "domain": ["Architecture"],
            "tone": "neutral",
            "format": "text",
            "constraints": [],
            "backend": self.backend,
        }

    def get_config(self, name: str) -> Optional[RefinementProfile]:
        return None


class CountingBackend(ModelBackend):
    constructed = 0
    unloaded = 0

    def __init__(self) -> None:
        type(self).constructed += 1
        self.last_error: Optional[str] = None

    def refine(self, prompt: str, profile: RefinementProfile) -> Optional[str]:
        return f"refined: {prompt} Architecture"

    def unload(self) -> None:
        type(self).unloaded += 1


class ExplodingBackend(ModelBackend):
    def __init__(self) -> None:
        raise RuntimeError("private constructor details")

    def refine(self, prompt: str, profile: RefinementProfile) -> Optional[str]:
        return None


@pytest.fixture(autouse=True)
def reset_test_backends():
    CountingBackend.constructed = 0
    CountingBackend.unloaded = 0
    BackendRegistry.register("counting-test", CountingBackend, replace=True)
    BackendRegistry.register("exploding-test", ExplodingBackend, replace=True)
    yield
    BackendRegistry.unregister("counting-test")
    BackendRegistry.unregister("exploding-test")


def test_refiner_reuses_backend_instances() -> None:
    refiner = PromptRefiner(StubProfileManager("counting-test"))

    assert refiner.refine("one") == "refined: one Architecture"
    assert refiner.refine("two") == "refined: two Architecture"
    assert CountingBackend.constructed == 1

    refiner.unload()
    assert CountingBackend.unloaded == 1


def test_refiner_unload_is_idempotent() -> None:
    refiner = PromptRefiner(StubProfileManager("counting-test"))
    refiner.refine("one")

    refiner.unload()
    refiner.unload()

    assert CountingBackend.unloaded == 1


def test_constructor_failure_uses_sanitized_rule_fallback() -> None:
    refiner = PromptRefiner(StubProfileManager("exploding-test"))

    result = refiner.refine("review this")

    assert "private constructor details" not in (refiner.last_warning or "")
    assert refiner.last_backend_used == "rule"
    assert "Tester" in result


def test_unknown_backend_uses_rule_fallback() -> None:
    refiner = PromptRefiner(StubProfileManager("missing-test"))

    result = refiner.refine("review this")

    assert refiner.last_backend_used == "rule"
    assert "Unknown backend" in (refiner.last_warning or "")
    assert "Tester" in result
