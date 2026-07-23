from typing import Optional

import pytest

from promptsmith.core.backends import ModelBackend
from promptsmith.core.backends.hybrid_backend import HybridBackend
from promptsmith.core.backends.rule_backend import RuleBasedBackend
from promptsmith.core.profile import RefinementProfile


class StubBackend(ModelBackend):
    def __init__(self, result: Optional[str], error: Optional[str] = None):
        self.result = result
        self.last_error = error
        self.calls = []
        self.unloaded = False

    def refine(self, prompt: str, profile: RefinementProfile) -> Optional[str]:
        self.calls.append((prompt, profile))
        return self.result

    def unload(self) -> None:
        self.unloaded = True


class StubLLMBackend(StubBackend):
    model_path = None

    def refine(
        self,
        prompt: str,
        profile: RefinementProfile,
        polish_mode: bool = False,
    ) -> Optional[str]:
        self.calls.append((prompt, profile, polish_mode))
        return self.result


def test_rule_backend_exposes_deterministic_rules_through_backend_contract():
    backend = RuleBasedBackend()
    result = backend.refine(
        "build a product card",
        RefinementProfile(role="React Developer", constraints=["Include tests."]),
    )

    assert result is not None
    assert "Act as if I am React Developer" in result
    assert "Include tests." in result
    assert backend.last_error is None


def test_hybrid_composes_injected_backends():
    rules = StubBackend("rule-refined prompt")
    llm = StubLLMBackend("a sufficiently complete polished prompt")
    backend = HybridBackend(rule_backend=rules, llm_backend=llm)

    result = backend.refine("raw prompt", RefinementProfile())

    assert result == "a sufficiently complete polished prompt"
    assert rules.calls == [("raw prompt", {})]
    assert llm.calls == [("rule-refined prompt", {}, True)]


def test_hybrid_returns_none_when_rule_backend_cannot_refine():
    rules = StubBackend(None, error="rules unavailable")
    llm = StubLLMBackend("unused polished prompt")
    backend = HybridBackend(rule_backend=rules, llm_backend=llm)

    assert backend.refine("raw prompt", RefinementProfile()) is None
    assert backend.last_error == "rules unavailable"
    assert llm.calls == []


def test_hybrid_unloads_all_composed_backends():
    rules = StubBackend("rule-refined prompt")
    llm = StubLLMBackend("a sufficiently complete polished prompt")
    backend = HybridBackend(rule_backend=rules, llm_backend=llm)

    backend.unload()

    assert rules.unloaded is True
    assert llm.unloaded is True


def test_hybrid_rejects_ambiguous_llm_configuration(tmp_path):
    with pytest.raises(ValueError, match="cannot both be supplied"):
        HybridBackend(
            model_path=tmp_path / "model.gguf",
            llm_backend=StubLLMBackend("unused"),
        )
