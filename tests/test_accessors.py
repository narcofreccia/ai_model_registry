"""Accessors, pricing (incl. variants) and the seeded catalog's shape."""

import json

import pytest

from ai_model_registry import load
from ai_model_registry.accessors import Registry

TIDE_SHARE_CHAT_ORDER = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-fable-5",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "glm-5.3-flash",
    "moonshotai/kimi-k3",
    "deepseek/deepseek-v4-pro",
    "zai/glm-5.3-flash",
]


@pytest.fixture(scope="module")
def registry():
    return load()


def test_active_chat_models_keep_tide_share_order(registry):
    active = [m.id for m in registry.models_by_kind("chat") if m.status == "active"]
    assert active == TIDE_SHARE_CHAT_ORDER


def test_models_by_kind_and_provider(registry):
    by_kind = registry.models_by_kind()
    assert set(by_kind) == {"chat", "embedding", "image_gen", "realtime"}
    assert len(registry.models_by_kind("embedding")) == 5
    assert [m.id for m in registry.models_by_provider("zai")] == ["glm-5.3-flash"]
    assert "anthropic" in registry.models_by_provider()


def test_get_by_id_alias_and_api_model_id(registry):
    assert registry.get("google_imagen_pro").id == "google_imagen_pro"
    assert registry.get("google/nano-banana-pro").id == "google_imagen_pro"
    assert registry.get("gemini-3-pro-image").id == "google_imagen_pro"
    assert registry.get("claude-sonnet-4-6-20250627").id == "claude-sonnet-4-6"
    assert registry.get("nope-not-a-model") is None


def test_every_provider_reference_resolves(registry):
    for model in registry.models:
        assert model.provider in registry.providers


def test_capability_facts_survive_the_round_trip(registry):
    opus = registry.get("claude-opus-5")
    assert (opus.reasoning, opus.allows_temperature, opus.server_web_tools) == (
        "adaptive", False, True,
    )
    sol = registry.get("gpt-5.6-sol")
    assert sol.responses_api is True
    assert sol.needs_pdf_rasterization is False  # gpt-5* ingests PDFs natively
    assert registry.get("gpt-4o").needs_pdf_rasterization is True
    assert registry.get("openai_gpt_image_2").max_reference_images == 16


def test_unknown_reasoning_mode_degrades_to_none(registry, caplog):
    data = json.loads(registry.model_dump_json())
    data["models"][0]["reasoning"] = "telepathy_2029"
    with caplog.at_level("WARNING"):
        degraded = Registry.model_validate(data)
    assert degraded.models[0].reasoning == "none"
    assert "telepathy_2029" in caplog.text


# --- pricing ---------------------------------------------------------------
def test_get_price_returns_base_price(registry):
    price = registry.get_price("claude-opus-5")
    assert (price.input_per_1m, price.output_per_1m) == (5.0, 25.0)
    assert registry.get_price("gemini-3.5-flash") is None  # unverified -> null


def test_get_price_applies_migrations(registry):
    assert registry.get_price("gpt-5.4") == registry.get_price("gpt-5.4")
    # a stale id resolves through the chain to the successor's price
    assert registry.get_price("gpt-5.2-codex") == registry.get_price("gpt-5.6-terra")


def test_cached_input_price_is_a_base_field(registry):
    assert registry.get_price("glm-5.3-flash").cached_input_per_1m == 0.03


def test_variants_default_to_empty(registry):
    assert registry.get_price("claude-opus-5").variants == ()


def test_variants_load_and_do_not_disturb_base_readers(registry):
    """A model carrying conditional rates still reads as a plain base price."""
    data = json.loads(registry.model_dump_json())
    target = next(m for m in data["models"] if m["id"] == "deepseek/deepseek-v4-pro")
    target["pricing"] = {
        "input_per_1m": 1.0,
        "output_per_1m": 2.0,
        "effective_from": "2026-08-01",
        "variants": [
            {"condition": "off_peak", "input_per_1m": 0.5, "output_per_1m": 1.0,
             "note": "16:30-00:30 UTC"},
            {"condition": "some_future_condition_we_do_not_know", "input_per_1m": 0.1},
        ],
    }
    loaded = Registry.model_validate(data)
    price = loaded.get_price("deepseek/deepseek-v4-pro")

    # a consumer reading only base fields is unaffected by the variants
    assert (price.input_per_1m, price.output_per_1m) == (1.0, 2.0)
    assert price.effective_from == "2026-08-01"
    # variants are available to consumers that want them, unknown ones included
    assert len(price.variants) == 2
    assert price.variant("off_peak").input_per_1m == 0.5
    assert price.variant("batch") is None


# --- realtime kind ---------------------------------------------------------
REALTIME_IDS = [
    "gpt-realtime-2.1",
    "gpt-realtime-2",
    "gpt-realtime-1.5",
    "gpt-audio-1.5",
    "gpt-4o-realtime-preview",
    "gpt-4o-mini-realtime-preview",
    "gemini-3.1-flash-live-preview",
    "gemini-live-2.5-flash-native-audio",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.5-flash-native-audio-preview-09-2025",
]


def test_realtime_models_are_all_present(registry):
    assert [m.id for m in registry.models_by_kind("realtime")] == REALTIME_IDS


def test_realtime_models_carry_voices_and_modalities(registry):
    for model_id in REALTIME_IDS:
        model = registry.get(model_id)
        assert model.voices, f"{model_id} has no voices"
        assert model.modalities, f"{model_id} has no modalities"
    openai_model = registry.get("gpt-realtime-2.1")
    assert len(openai_model.voices) == 12
    assert "coral" in openai_model.voices
    assert openai_model.modalities == ("text", "audio")
    google_model = registry.get("gemini-3.1-flash-live-preview")
    assert len(google_model.voices) == 30
    assert "Puck" in google_model.voices
    assert google_model.modalities == ("AUDIO",)


def test_realtime_pricing_reads_on_the_audio_text_axes(registry):
    price = registry.get_price("gpt-realtime-2.1")
    assert price.is_realtime
    assert (price.audio_input_per_1m, price.audio_output_per_1m) == (32.0, 64.0)
    assert (price.text_input_per_1m, price.text_output_per_1m) == (4.0, 24.0)
    assert price.cached_input_per_1m == 0.4
    assert price.cached_audio_input_per_1m is None
    # the chat axis stays empty, so a chat-only reader sees "no price" fields
    assert (price.input_per_1m, price.output_per_1m, price.per_image) == (None, None, None)


def test_chat_pricing_is_not_flagged_realtime(registry):
    assert registry.get_price("claude-opus-5").is_realtime is False


def test_realtime_migrations_chain_to_the_flagship(registry):
    assert registry.resolve_migration("gpt-realtime-1.5") == "gpt-realtime-2.1"
    assert registry.resolve_migration("gpt-4o-realtime-preview") == "gpt-realtime-2.1"
    assert registry.resolve_migration("gpt-4o-mini-realtime-preview") == "gpt-realtime-2.1"
    assert (
        registry.resolve_migration("gemini-2.5-flash-native-audio-preview-09-2025")
        == "gemini-2.5-flash-native-audio-preview-12-2025"
    )


def test_deprecated_realtime_ids_stay_callable_verbatim(registry):
    """House rule: deprecated = still callable. The entry (and its own price)
    must survive lookup without being replaced by the migration target."""
    for model_id in ("gpt-realtime-2", "gpt-realtime-1.5", "gpt-4o-realtime-preview"):
        model = registry.get(model_id)
        assert model.id == model_id
        assert model.status == "deprecated"
    # NOTE: get_price() migrates first (registry-wide behavior), so a deprecated
    # id reads the SUCCESSOR's rates. A biller charging a deprecated id verbatim
    # must read `registry.get(id).pricing` instead — these differ here.
    assert registry.get("gpt-realtime-1.5").pricing.text_output_per_1m == 16.0
    assert registry.get_price("gpt-realtime-1.5").text_output_per_1m == 24.0
    assert registry.get("gpt-4o-mini-realtime-preview").pricing.audio_input_per_1m == 10.0


def test_old_snapshots_without_the_new_fields_still_load(registry):
    """Adapter tolerance in the other direction: a pre-realtime registry has no
    `modalities` and no `schema_minor`."""
    data = json.loads(registry.model_dump_json())
    data.pop("schema_minor", None)
    data["models"] = [m for m in data["models"] if m["kind"] != "realtime"]
    for model in data["models"]:
        model.pop("modalities", None)
    loaded = Registry.model_validate(data)
    assert loaded.schema_minor == 0
    assert loaded.models[0].modalities is None
    assert loaded.models_by_kind("realtime") == []
