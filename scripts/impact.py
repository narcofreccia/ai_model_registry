#!/usr/bin/env python3
"""What a candidate registry.json changes for ids consumers already store.

    python3 scripts/impact.py                 # candidate registry.json vs the `stable` tag
    python3 scripts/impact.py --old v0.5.4    # ...vs any git ref

Both files are read through this repo's own adapter (`Registry`), so the report
uses the same resolution rules consumers run. Three lists:
  - models whose status changed;
  - ids whose `resolve_usable` changed: what a stored id is now CALLED as;
  - ids whose full-chain `resolve_migration` changed: what `get_price` / `resolve` read.
New ids are not impact. Informational only: `release.py` prints it and goes on.
Also imported by `release.py` and tests/test_impact.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # this repo's adapter, not whatever is installed

from ai_model_registry.accessors import Registry  # noqa: E402


@dataclass
class Impact:
    status: list[tuple[str, str, str]] = field(default_factory=list)  # (model id, old, new)
    usable: list[tuple[str, str, str]] = field(default_factory=list)  # (stored id, old, new)
    full_chain: list[tuple[str, str, str]] = field(default_factory=list)  # (stored id, old, new)

    def __bool__(self) -> bool:
        return bool(self.status or self.usable or self.full_chain)


def stored_ids(registry: Registry) -> set[str]:
    """Every id a consumer may have saved: model ids, aliases, api_model_ids, migration keys."""
    ids = set(registry.migrations)
    for model in registry.models:
        ids.update((model.id, model.api_model_id, *model.aliases))
    return ids


def status_of(registry: Registry, model_id: str) -> str | None:
    model = registry.get(model_id)
    return model.status if model else None


def compute(old: Registry, new: Registry) -> Impact:
    """Compare two registries over the union of their stored ids, sorted."""
    impact = Impact()
    old_ids = {m.id for m in old.models}
    for model in new.models:
        if model.id in old_ids and status_of(old, model.id) != model.status:
            impact.status.append((model.id, status_of(old, model.id), model.status))
    for stored in sorted(stored_ids(old) | stored_ids(new)):
        before, after = old.resolve_usable(stored), new.resolve_usable(stored)
        if before != after:
            impact.usable.append((stored, before, after))
        before, after = old.resolve_migration(stored), new.resolve_migration(stored)
        if before != after:
            impact.full_chain.append((stored, before, after))
    impact.status.sort()
    return impact


def report(impact: Impact) -> list[str]:
    """Printable lines; one line when nothing a consumer stores changes meaning."""
    if not impact:
        return ["no stored id changes meaning"]
    lines = []
    if impact.status:
        lines.append("status changed:")
        lines += [f"  {mid}: {old} -> {new}" for mid, old, new in impact.status]
    if impact.usable:
        lines.append("called differently (resolve_usable, what an app sends):")
        lines += [f"  a stored {sid} will now be called as {new}, was {old}" for sid, old, new in impact.usable]
    else:
        lines.append("called differently (resolve_usable): none")
    if impact.full_chain:
        lines.append("full chain changed (resolve_migration: get_price, resolve):")
        lines += [f"  {sid}: {old} -> {new}" for sid, old, new in impact.full_chain]
    return lines


def parse(text: str) -> Registry:
    return Registry.model_validate(json.loads(text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old", default="stable", help="git ref of the published registry (default: stable)")
    parser.add_argument("--new", default=str(REPO / "registry.json"), help="candidate file (default: registry.json)")
    args = parser.parse_args()
    from consumers import show  # git helper; imported here so tests need no git

    old_text = show(args.old, "registry.json")
    if old_text is None:
        sys.exit(f"no registry.json at {args.old}")
    print("\n".join(report(compute(parse(old_text), parse(Path(args.new).read_text())))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
