"""resolve_usable: the id to CALL now, migrating only a retired (or unknown) id.

resolve_migration follows a chain to its end; resolve_usable stops at the first
model that still answers. The v0.5.3 incident is the reason both exist.
"""

import pytest

from ai_model_registry import load
from ai_model_registry.accessors import Registry


def make(models, migrations):
    """A minimal in-memory registry: models as (id, status, aliases)."""
    return Registry.model_validate({
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "providers": {"openai": {"name": "OpenAI"}},
        "models": [
            {"id": mid, "name": mid, "provider": "openai", "api_model_id": f"api-{mid}",
             "aliases": list(aliases), "status": status}
            for mid, status, aliases in models
        ],
        "migrations": migrations,
    })


@pytest.fixture
def chain():
    # retired A -> deprecated B -> active C: the v0.5.3 shape
    return make(
        [("a", "retired", ()), ("b", "deprecated", ("b-alias",)), ("c", "active", ()),
         ("r1", "retired", ()), ("r2", "retired", ())],
        {"a": "b", "b": "c", "r1": "r2", "r2": "c", "vendor/a": "a"},
    )


def test_active_id_verbatim(chain):
    assert chain.resolve_usable("c") == "c"
    assert chain.usable("c").id == "c"


def test_deprecated_id_verbatim(chain):
    assert chain.resolve_usable("b") == "b"
    assert chain.resolve_migration("b") == "c"


def test_alias_and_api_id_of_a_deprecated_model_verbatim(chain):
    assert chain.resolve_usable("b-alias") == "b-alias"
    assert chain.resolve_usable("api-b") == "api-b"
    assert chain.usable("b-alias").id == "b"


def test_retired_stops_at_the_first_callable_hop(chain):
    assert chain.resolve_usable("a") == "b"
    assert chain.resolve_migration("a") == "c"
    assert chain.usable("a").status == "deprecated"


def test_retired_through_retired_to_active(chain):
    assert chain.resolve_usable("r1") == "c"


def test_unknown_id_with_a_migration_key(chain):
    assert chain.resolve_usable("vendor/a") == "b"
    assert chain.resolve_migration("vendor/a") == "c"


def test_unknown_id_without_a_migration_passes_through(chain):
    assert chain.resolve_usable("someone/new-model") == "someone/new-model"
    assert chain.usable("someone/new-model") is None


def test_dead_end_on_a_retired_model_returns_it():
    registry = make([("old", "retired", ())], {})
    assert registry.resolve_usable("old") == "old"


def test_alias_of_a_retired_model_follows_the_canonical_migration():
    registry = make([("old", "retired", ("old-dated",)), ("new", "active", ())], {"old": "new"})
    assert registry.resolve_usable("old-dated") == "new"


def test_cycle_terminates():
    registry = make([("a", "retired", ())], {"x": "y", "y": "x", "a": "z", "z": "a"})
    assert registry.resolve_usable("x") in {"x", "y"}
    assert registry.resolve_usable("a") in {"a", "z"}


def test_other_accessors_still_follow_the_full_chain(chain):
    assert chain.resolve("a").id == "c"
    assert chain.get("a").id == "a"


# -- real data ------------------------------------------------------------
@pytest.fixture(scope="module")
def registry():
    return load()


def test_real_retired_image_ids_land_on_gpt_image_2(registry):
    for old in ("gpt-image-1.5", "openai/gpt-image-1.5", "dall-e-3"):
        assert registry.resolve_usable(old) == "openai_gpt_image_2"


def test_real_deprecated_ids_stay_verbatim(registry):
    for model_id in ("gpt-realtime-1.5", "claude-opus-4-7"):
        assert registry.get(model_id).status == "deprecated"
        assert registry.resolve_usable(model_id) == model_id
        assert registry.resolve_migration(model_id) != model_id


def test_real_usable_is_never_retired_for_a_migrated_id(registry):
    for old in registry.migrations:
        assert registry.usable(old).status != "retired", old
