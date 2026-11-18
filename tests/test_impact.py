"""scripts/impact.py: what a candidate registry changes for ids consumers already store."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def impact():
    spec = importlib.util.spec_from_file_location("registry_impact", REPO / "scripts" / "impact.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks the module up while decorating
    spec.loader.exec_module(module)
    return module


def make(impact, models, migrations):
    return impact.Registry.model_validate({
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "providers": {"openai": {"name": "OpenAI"}},
        "models": [
            {"id": mid, "name": mid, "provider": "openai", "api_model_id": mid, "status": status}
            for mid, status in models
        ],
        "migrations": migrations,
    })


def test_deprecating_a_hop_moves_the_full_chain_not_the_usable_id(impact):
    """v0.5.3: retired A -> B; B goes active -> deprecated with B -> C."""
    old = make(impact, [("a", "retired"), ("b", "active"), ("c", "active")], {"a": "b", "vendor/a": "a"})
    new = make(impact, [("a", "retired"), ("b", "deprecated"), ("c", "active")], {"a": "b", "vendor/a": "a", "b": "c"})
    result = impact.compute(old, new)
    assert result.status == [("b", "active", "deprecated")]
    assert result.usable == []
    assert result.full_chain == [("a", "b", "c"), ("b", "b", "c"), ("vendor/a", "b", "c")]
    lines = impact.report(result)
    assert "  a: b -> c" in lines
    assert "called differently (resolve_usable): none" in lines


def test_retiring_a_hop_changes_what_is_called(impact):
    old = make(impact, [("a", "retired"), ("b", "deprecated"), ("c", "active")], {"a": "b", "b": "c"})
    new = make(impact, [("a", "retired"), ("b", "retired"), ("c", "active")], {"a": "b", "b": "c"})
    result = impact.compute(old, new)
    assert result.usable == [("a", "b", "c"), ("b", "b", "c")]
    assert result.full_chain == []
    assert "  a stored a will now be called as c, was b" in impact.report(result)


def test_new_models_are_not_impact(impact):
    old = make(impact, [("a", "active")], {})
    new = make(impact, [("a", "active"), ("n", "active")], {})
    result = impact.compute(old, new)
    assert not result
    assert impact.report(result) == ["no stored id changes meaning"]


def test_real_registry_against_itself_is_quiet(impact):
    registry = impact.parse((REPO / "registry.json").read_text())
    assert impact.report(impact.compute(registry, registry)) == ["no stored id changes meaning"]
