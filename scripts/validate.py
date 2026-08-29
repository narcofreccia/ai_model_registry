#!/usr/bin/env python3
"""Validate registry.json: schema + the invariants consumers rely on.

Run from anywhere:  python3 scripts/validate.py
Exit code 0 = green, 1 = one or more failures (all reported, not just the first).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "registry.json"
SCHEMA_PATH = REPO / "schema" / "registry.schema.json"
STABLE_REF = "stable"

failures: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


# ---------------------------------------------------------------------------
# 1. schema
# ---------------------------------------------------------------------------
def check_schema(registry: dict) -> None:
    try:
        import jsonschema
    except ImportError:
        fail("jsonschema is not installed (pip install jsonschema)")
        return
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(registry), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in error.path) or "<root>"
        fail(f"schema: {location}: {error.message}")


# ---------------------------------------------------------------------------
# 2. uniqueness of ids / aliases / api_model_ids
# ---------------------------------------------------------------------------
def check_uniqueness(models: list[dict]) -> None:
    ids: dict[str, int] = {}
    for model in models:
        model_id = model.get("id", "")
        if model_id in ids:
            fail(f"duplicate model id: {model_id!r}")
        ids[model_id] = 1

    seen_aliases: dict[str, str] = {}
    for model in models:
        for alias in model.get("aliases", []):
            if alias in ids:
                fail(f"alias {alias!r} (on {model['id']!r}) collides with a model id")
            if alias in seen_aliases:
                fail(
                    f"duplicate alias {alias!r}: on {seen_aliases[alias]!r} "
                    f"and {model['id']!r}"
                )
            seen_aliases[alias] = model["id"]

    seen_api: dict[str, str] = {}
    for model in models:
        api_id = model.get("api_model_id", "")
        if api_id in seen_api:
            fail(
                f"duplicate api_model_id {api_id!r}: on {seen_api[api_id]!r} "
                f"and {model['id']!r}"
            )
        seen_api[api_id] = model["id"]


# ---------------------------------------------------------------------------
# 3. provider references
# ---------------------------------------------------------------------------
def check_providers(registry: dict) -> None:
    providers = set(registry.get("providers", {}))
    for model in registry.get("models", []):
        if model.get("provider") not in providers:
            fail(
                f"model {model.get('id')!r} references unknown provider "
                f"{model.get('provider')!r}"
            )


# ---------------------------------------------------------------------------
# 4. migrations: chained, cycle-safe, terminating at a real model id
# ---------------------------------------------------------------------------
def resolve(migrations: dict[str, str], model_id: str) -> tuple[str, bool]:
    """Chained resolution. Returns (final_id, hit_cycle)."""
    seen: set[str] = set()
    current = model_id
    while current in migrations:
        if current in seen:
            return current, True
        seen.add(current)
        current = migrations[current]
    return current, False


def check_migrations(registry: dict) -> None:
    migrations: dict[str, str] = registry.get("migrations", {})
    ids = {m.get("id") for m in registry.get("models", [])}
    for old in migrations:
        final, cycle = resolve(migrations, old)
        if cycle:
            fail(f"migration cycle reached from {old!r} (loops at {final!r})")
            continue
        if final not in ids:
            fail(f"migration {old!r} resolves to {final!r}, which is not a model id")


# ---------------------------------------------------------------------------
# 5. lifecycle: retired/deprecated ids need a migration
# ---------------------------------------------------------------------------
def check_lifecycle(registry: dict) -> None:
    migrations = registry.get("migrations", {})
    for model in registry.get("models", []):
        if model.get("status") in {"deprecated", "retired"} and model["id"] not in migrations:
            fail(
                f"model {model['id']!r} is {model['status']} but has no migrations "
                f"entry — old saved ids would dead-end"
            )


# ---------------------------------------------------------------------------
# 6. diff vs the published `stable` registry
# ---------------------------------------------------------------------------
def check_against_stable(registry: dict) -> None:
    try:
        published = subprocess.run(
            ["git", "show", f"{STABLE_REF}:registry.json"],
            cwd=REPO,
            capture_output=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        notes.append(
            f"no `{STABLE_REF}` ref yet — skipping the removed-model check "
            f"(expected before the first promotion)"
        )
        return

    try:
        old = json.loads(published)
    except json.JSONDecodeError as exc:
        fail(f"{STABLE_REF}:registry.json is not valid JSON: {exc}")
        return

    old_ids = {m.get("id") for m in old.get("models", [])}
    new_ids = {m.get("id") for m in registry.get("models", [])}
    migrations = registry.get("migrations", {})
    for removed in sorted(old_ids - new_ids):
        if removed not in migrations:
            fail(
                f"model {removed!r} was removed since `{STABLE_REF}` without a "
                f"migrations entry — consumers with that id saved would break"
            )


def main() -> int:
    try:
        registry = json.loads(REGISTRY_PATH.read_text())
    except Exception as exc:
        print(f"FAIL  cannot read {REGISTRY_PATH}: {exc}")
        return 1

    check_schema(registry)
    models = registry.get("models", [])
    if isinstance(models, list):
        check_uniqueness(models)
    check_providers(registry)
    check_migrations(registry)
    check_lifecycle(registry)
    check_against_stable(registry)

    for note in notes:
        print(f"note  {note}")

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        print(f"\n{len(failures)} problem(s) in registry.json")
        return 1

    kinds: dict[str, int] = {}
    for model in models:
        kinds[model.get("kind", "?")] = kinds.get(model.get("kind", "?"), 0) + 1
    priced = sum(1 for m in models if m.get("pricing"))
    print(
        f"OK    {len(models)} models ("
        + ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items()))
        + f"), {len(registry.get('migrations', {}))} migrations, "
        f"{priced} priced / {len(models) - priced} unpriced, "
        f"{len(registry.get('providers', {}))} providers"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
