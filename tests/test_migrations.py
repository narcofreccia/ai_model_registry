"""Migration chaining — the contract that keeps stale saved ids working."""

import pytest

from ai_model_registry import load
from ai_model_registry.accessors import Registry


@pytest.fixture(scope="module")
def registry():
    return load()


@pytest.mark.parametrize(
    "old,expected",
    [
        # tide_share chains
        ("claude-opus-4-20250514", "claude-opus-5"),   # dated -> 4.8 -> opus-5
        ("claude-opus-4-7", "claude-opus-5"),
        ("claude-3-5-haiku-latest", "claude-haiku-4-5"),
        ("gpt-4o", "gpt-5.6-terra"),                   # -> gpt-5.4 -> terra
        ("gpt-4o-mini", "gpt-5.6-luna"),               # -> gpt-5.4-mini -> luna
        ("gpt-5.2-pro", "gpt-5.6-sol"),                # -> gpt-5.5 -> sol
        ("gpt-5-nano", "gpt-5.6-luna"),
        ("gpt-5.6", "gpt-5.6-sol"),
        ("gemini-3-pro-preview", "gemini-3.1-pro-preview"),
        ("stability", "google_imagen_pro"),
        # ndr_backend ids
        ("gpt-4.1", "gpt-5.6-terra"),
        ("gpt-4.1-mini", "gpt-5.6-luna"),
        ("o3", "gpt-5.6-sol"),
        ("claude-sonnet-4", "claude-sonnet-5"),
        ("claude-sonnet-4-5", "claude-sonnet-5"),
        ("claude-sonnet-4-5-20250514", "claude-sonnet-5"),  # ndr's wrong date suffix
        ("claude-sonnet-4-6", "claude-sonnet-5"),
        ("claude-opus-4-6", "claude-opus-5"),
        ("gpt-image-1.5", "openai_gpt_image_2"),
        ("openai/gpt-image-1.5", "openai_gpt_image_2"),
    ],
)
def test_known_migrations_resolve(registry, old, expected):
    assert registry.resolve_migration(old) == expected
    assert registry.resolve(old).id == expected


def test_unknown_id_passes_through(registry):
    assert registry.resolve_migration("openrouter:some/new-model") == "openrouter:some/new-model"
    assert registry.resolve("openrouter:some/new-model") is None


def test_every_migration_target_is_a_real_model(registry):
    for old in registry.migrations:
        assert registry.resolve(old) is not None, old


def test_every_deprecated_or_retired_model_has_a_migration(registry):
    for model in registry.models:
        if model.status in {"deprecated", "retired"}:
            assert model.id in registry.migrations, model.id
            assert registry.resolve(model.id).status == "active"


def test_resolution_is_cycle_safe():
    data = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "providers": {"openai": {"name": "OpenAI"}},
        "models": [
            {"id": "a", "name": "A", "provider": "openai", "api_model_id": "a"},
        ],
        "migrations": {"x": "y", "y": "x"},
    }
    registry = Registry.model_validate(data)
    # terminates instead of spinning forever
    assert registry.resolve_migration("x") in {"x", "y"}
