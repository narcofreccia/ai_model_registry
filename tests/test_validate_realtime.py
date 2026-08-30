"""scripts/validate.py's realtime invariants (voices + pricing shape)."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def validate():
    """A fresh import of scripts/validate.py (it keeps module-level state)."""
    spec = importlib.util.spec_from_file_location(
        "registry_validate", REPO / "scripts" / "validate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.failures.clear()
    return module


def _realtime_model(**overrides) -> dict:
    model = {
        "id": "rt-test",
        "name": "RT Test",
        "description": "",
        "provider": "openai",
        "kind": "realtime",
        "api_model_id": "rt-test",
        "aliases": [],
        "reasoning": "none",
        "allows_temperature": True,
        "responses_api": False,
        "server_web_tools": False,
        "vision": False,
        "needs_pdf_rasterization": False,
        "max_reference_images": None,
        "voices": ["coral"],
        "modalities": ["text", "audio"],
        "status": "active",
        "pricing": {
            "audio_input_per_1m": 32.0,
            "audio_output_per_1m": 64.0,
            "text_input_per_1m": 4.0,
            "text_output_per_1m": 24.0,
            "cached_input_per_1m": 0.4,
        },
    }
    model.update(overrides)
    return {"models": [model]}


def test_the_shipped_registry_passes_every_invariant(validate):
    registry = json.loads((REPO / "registry.json").read_text())
    validate.check_schema(registry)
    validate.check_uniqueness(registry["models"])
    validate.check_providers(registry)
    validate.check_migrations(registry)
    validate.check_lifecycle(registry)
    validate.check_realtime(registry)
    assert validate.failures == []


def test_realtime_without_voices_fails(validate):
    validate.check_realtime(_realtime_model(voices=None))
    assert any("no voices" in f for f in validate.failures)
    validate.failures.clear()
    validate.check_realtime(_realtime_model(voices=[]))
    assert any("no voices" in f for f in validate.failures)


def test_realtime_priced_on_the_chat_axis_fails(validate):
    validate.check_realtime(
        _realtime_model(pricing={"input_per_1m": 32.0, "output_per_1m": 64.0})
    )
    assert any("chat/image axis" in f for f in validate.failures)


def test_realtime_mixing_in_chat_rate_keys_fails(validate):
    pricing = _realtime_model()["models"][0]["pricing"] | {"input_per_1m": 1.0}
    validate.check_realtime(_realtime_model(pricing=pricing))
    assert any("mixes chat/image rate keys" in f for f in validate.failures)


def test_chat_model_with_realtime_rate_keys_fails(validate):
    validate.check_realtime(
        _realtime_model(kind="chat", pricing={"audio_input_per_1m": 32.0})
    )
    assert any("only kind 'realtime'" in f for f in validate.failures)


def test_unpriced_realtime_model_is_allowed(validate):
    """Never invent a price: a realtime model with no verified rate is valid."""
    validate.check_realtime(_realtime_model(pricing=None))
    assert validate.failures == []
