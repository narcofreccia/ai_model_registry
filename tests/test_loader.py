"""Loader precedence and offline behavior."""

import json

import pytest

from ai_model_registry import load
from ai_model_registry import loader as loader_module


def test_load_packaged_by_default():
    registry = load()
    assert registry.schema_version == 1
    assert registry.get("claude-opus-5") is not None


def test_snapshot_beats_packaged(make_registry_file):
    path = make_registry_file("snap.json", generated_at="1999-01-01T00:00:00Z")
    assert load(snapshot_path=path).generated_at == "1999-01-01T00:00:00Z"


def test_cache_beats_snapshot(tmp_path, make_registry_file):
    snapshot = make_registry_file("snap.json", generated_at="1999-01-01T00:00:00Z")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    make_registry_file("cache/registry.json", generated_at="2020-02-02T00:00:00Z")
    registry = load(snapshot_path=snapshot, cache_dir=cache_dir)
    assert registry.generated_at == "2020-02-02T00:00:00Z"


def test_fetch_beats_everything_and_refreshes_cache(tmp_path, monkeypatch, registry_dict):
    fetched = dict(registry_dict, generated_at="2030-03-03T00:00:00Z")
    monkeypatch.setattr(
        loader_module, "_fetch", lambda url, errors: json.dumps(fetched).encode()
    )
    cache_dir = tmp_path / "cache"
    registry = load(cache_dir=cache_dir, fetch=True)
    assert registry.generated_at == "2030-03-03T00:00:00Z"
    # the fetched copy became the new last-good cache
    cached = json.loads((cache_dir / "registry.json").read_text())
    assert cached["generated_at"] == "2030-03-03T00:00:00Z"


def test_offline_fetch_falls_back_to_cache(tmp_path, make_registry_file):
    """A dead URL must not raise while any fallback exists."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    make_registry_file("cache/registry.json", generated_at="2020-02-02T00:00:00Z")
    registry = load(
        cache_dir=cache_dir,
        fetch=True,
        url="http://127.0.0.1:9/registry.json",  # discard port: always refused
    )
    assert registry.generated_at == "2020-02-02T00:00:00Z"


def test_offline_fetch_falls_back_to_packaged():
    registry = load(fetch=True, url="http://127.0.0.1:9/registry.json")
    assert registry.get("gpt-5.6-sol") is not None


def test_corrupt_snapshot_falls_back_to_packaged(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load(snapshot_path=bad).get("claude-sonnet-5") is not None


def test_missing_snapshot_falls_back_to_packaged(tmp_path):
    assert load(snapshot_path=tmp_path / "nope.json").schema_version == 1


def test_raises_only_when_every_source_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        loader_module, "_load_packaged", lambda errors: (errors.append("no package"), None)[1]
    )
    with pytest.raises(RuntimeError):
        load(snapshot_path=tmp_path / "nope.json")


# -- AI_MODEL_REGISTRY_FILE ------------------------------------------------
def test_override_env_name_is_exported():
    import ai_model_registry

    assert ai_model_registry.OVERRIDE_ENV == "AI_MODEL_REGISTRY_FILE"


def test_override_wins_over_fetch_cache_and_snapshot(tmp_path, monkeypatch, make_registry_file):
    override = make_registry_file("candidate.json", generated_at="2040-04-04T00:00:00Z")
    snapshot = make_registry_file("snap.json", generated_at="1999-01-01T00:00:00Z")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    make_registry_file("cache/registry.json", generated_at="2020-02-02T00:00:00Z")
    fetched = []
    monkeypatch.setattr(loader_module, "_fetch", lambda url, errors: fetched.append(url))
    monkeypatch.setenv("AI_MODEL_REGISTRY_FILE", str(override))

    registry = load(snapshot_path=snapshot, cache_dir=cache_dir, fetch=True, url="http://x/r.json")
    assert registry.generated_at == "2040-04-04T00:00:00Z"
    assert fetched == []  # never touched the network
    cached = json.loads((cache_dir / "registry.json").read_text())
    assert cached["generated_at"] == "2020-02-02T00:00:00Z"  # cache not rewritten


def test_override_writes_no_cache(tmp_path, monkeypatch, make_registry_file):
    monkeypatch.setenv("AI_MODEL_REGISTRY_FILE", str(make_registry_file("candidate.json")))
    load(cache_dir=tmp_path / "fresh_cache", fetch=True)
    assert not (tmp_path / "fresh_cache").exists()


def test_override_missing_file_raises(tmp_path, monkeypatch, make_registry_file):
    monkeypatch.setenv("AI_MODEL_REGISTRY_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(RuntimeError, match="AI_MODEL_REGISTRY_FILE"):
        load(snapshot_path=make_registry_file("snap.json"))


def test_override_invalid_file_raises(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setenv("AI_MODEL_REGISTRY_FILE", str(bad))
    with pytest.raises(RuntimeError, match="invalid registry"):
        load()


@pytest.mark.parametrize("value", [None, "", "  "])
def test_unset_or_empty_override_keeps_the_normal_order(monkeypatch, make_registry_file, value):
    if value is None:
        monkeypatch.delenv("AI_MODEL_REGISTRY_FILE", raising=False)
    else:
        monkeypatch.setenv("AI_MODEL_REGISTRY_FILE", value)
    path = make_registry_file("snap.json", generated_at="1999-01-01T00:00:00Z")
    assert load(snapshot_path=path).generated_at == "1999-01-01T00:00:00Z"
