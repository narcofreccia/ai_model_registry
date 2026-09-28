"""The `decision` kind (schema_minor 2): TypeSafe Jev, its validate.py
invariants, and adapter tolerance for kinds newer than the adapter."""

import importlib.util
import json
from pathlib import Path

import pytest

from ai_model_registry import load
from ai_model_registry.accessors import Registry

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry():
    return load()


@pytest.fixture()
def validate():
    spec = importlib.util.spec_from_file_location(
        "registry_validate_decision", REPO / "scripts" / "validate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.failures.clear()
    return module


# --- the shipped entry ------------------------------------------------------
def test_jev_resolves_by_id_alias_and_api_model_id(registry):
    assert registry.get("jev-1.13").id == "jev-1.13"
    assert registry.get("jev-latest").id == "jev-1.13"
    assert registry.get("jev-1.13.0").id == "jev-1.13"
    assert [m.id for m in registry.models_by_kind("decision")] == ["jev-1.13"]


def test_jev_facts_round_trip(registry):
    jev = registry.get("jev-1.13")
    assert jev.kind == "decision"
    assert jev.provider == "typesafe"
    assert jev.api_model_id == "jev-1.13.0"
    assert (jev.reasoning, jev.allows_temperature, jev.vision) == ("none", False, False)
    assert (jev.responses_api, jev.server_web_tools) == (False, False)
    assert jev.question_types == ("noul", "choice", "score")
    assert (jev.max_request_tokens, jev.max_state_question_tokens) == (64000, 32000)
    assert (jev.max_choice_options, jev.max_score_levels) == (255, 10)
    assert jev.voices is None and jev.modalities is None


def test_typesafe_provider(registry):
    provider = registry.providers["typesafe"]
    assert provider.base_url == "https://api.typesafe.ai"
    assert provider.key_env == "TYPESAFE_API_KEY"
    assert provider.pydantic_ai_prefix == "typesafe"


def test_jev_pricing_is_input_only_on_the_token_shape(registry):
    price = registry.get_price("jev-latest")
    assert (price.input_per_1m, price.output_per_1m) == (0.042, 0.0)
    assert price.is_realtime is False


def test_decision_models_stay_out_of_chat(registry):
    chat_ids = {m.id for m in registry.models_by_kind("chat")}
    assert "jev-1.13" not in chat_ids


def test_non_decision_models_carry_no_decision_fields(registry):
    for model in registry.models:
        if model.kind != "decision":
            assert model.question_types is None, model.id
            assert model.max_request_tokens is None, model.id


# --- adapter tolerance -------------------------------------------------------
def test_unknown_kind_loads_and_is_filtered_out(registry, caplog):
    """A kind newer than this adapter must not reject the whole registry."""
    data = json.loads(registry.model_dump_json())
    data["models"][0]["kind"] = "hologram_2029"
    with caplog.at_level("WARNING"):
        loaded = Registry.model_validate(data)
    assert loaded.models[0].kind == "hologram_2029"
    assert "hologram_2029" in caplog.text
    assert data["models"][0]["id"] not in {m.id for m in loaded.models_by_kind("chat")}
    assert loaded.models_by_kind("hologram_2029")[0].id == data["models"][0]["id"]


# --- validate.py invariants --------------------------------------------------
def _decision_model(**overrides) -> dict:
    model = {
        "id": "dec-test",
        "kind": "decision",
        "question_types": ["noul"],
        "pricing": {"input_per_1m": 0.1, "output_per_1m": 0.0},
    }
    model.update(overrides)
    return {"models": [model]}


def test_valid_decision_model_passes(validate):
    validate.check_decision(_decision_model())
    assert validate.failures == []


def test_decision_without_question_types_fails(validate):
    validate.check_decision(_decision_model(question_types=None))
    assert any("no question_types" in f for f in validate.failures)


def test_decision_priced_per_image_fails(validate):
    validate.check_decision(_decision_model(pricing={"per_image": 0.01}))
    assert any("token shape" in f for f in validate.failures)


def test_unpriced_decision_model_is_allowed(validate):
    validate.check_decision(_decision_model(pricing=None))
    assert validate.failures == []


def test_decision_fields_on_a_chat_model_fail(validate):
    validate.check_decision(_decision_model(kind="chat"))
    assert any("decision-only fields" in f for f in validate.failures)
