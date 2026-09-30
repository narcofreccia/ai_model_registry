#!/usr/bin/env python3
"""The repos that install this package, and which registry pin each one is on.

The list lives in `consumers.json` at the repo root (gitignored: the paths are
machine-specific; the shape is in `consumers.example.json`).

    python3 scripts/consumers.py status              # committed pin, adapter version, can it read `stable`?
    python3 scripts/consumers.py discover            # scan sibling dirs for pins
    python3 scripts/consumers.py discover --write    # ...and add new ones to consumers.json

Also imported by `update_consumers.py` and `release.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONSUMERS_PATH = REPO / "consumers.json"
GIT_URL = "https://github.com/narcofreccia/ai_model_registry.git"
RAW_URL = "https://raw.githubusercontent.com/narcofreccia/ai_model_registry/{ref}/registry.json"

# `ai_model_registry.git@<ref>` inside a requirements line or a pyproject string.
PIN_RE = re.compile(r"(narcofreccia/ai_model_registry\.git@)([A-Za-z0-9._/-]+)")
PIN_FILE_NAMES = ("requirements.txt", "pyproject.toml")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "site-packages", "build", "dist", "__pycache__"}


@dataclass
class Consumer:
    name: str
    path: str
    pin_files: list[str]
    snapshot: str | None = None
    python: str = "venv/bin/python"
    test_cwd: str = "."
    test: list[str] = field(default_factory=lambda: ["-m", "pytest", "-q"])
    followups: list[str] = field(default_factory=list)

    @property
    def root(self) -> Path:
        return (REPO / self.path).resolve()


def load_consumers(path: Path = CONSUMERS_PATH) -> list[Consumer]:
    if not path.exists():
        sys.exit(
            f"{path.name} not found. Create it from consumers.example.json, or run\n"
            f"  python3 scripts/consumers.py discover --write"
        )
    data = json.loads(path.read_text())
    return [Consumer(**entry) for entry in data["consumers"]]


def read_pins(text: str) -> list[str]:
    return [m.group(2) for m in PIN_RE.finditer(text)]


def rewrite_pins(text: str, new_ref: str) -> tuple[str, int]:
    """Point every registry pin in `text` at `new_ref`; returns (text, count)."""
    return PIN_RE.subn(lambda m: m.group(1) + new_ref, text)


def consumer_pins(consumer: Consumer, committed: bool = False) -> dict[str, list[str]]:
    """Pins per pin file: the working tree, or with `committed` the repo's HEAD —
    an uncommitted edit (e.g. from update_consumers.py) is not what runs anywhere."""
    pins: dict[str, list[str]] = {}
    for rel in consumer.pin_files:
        if committed:
            result = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=consumer.root, capture_output=True, text=True)
            pins[rel] = read_pins(result.stdout) if result.returncode == 0 else []
        else:
            file = consumer.root / rel
            pins[rel] = read_pins(file.read_text()) if file.exists() else []
    return pins


def unpushed(consumer: Consumer) -> bool:
    """HEAD has commits touching a pin file that its upstream branch does not."""
    result = subprocess.run(
        ["git", "rev-list", "--count", "@{u}..HEAD", "--", *consumer.pin_files],
        cwd=consumer.root, capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != "0"


def shas_of(pins: dict[str, list[str]]) -> list[str]:
    return sorted({s for found in pins.values() for s in found})


# ---------------------------------------------------------------------------
# git helpers (run in this repo)
# ---------------------------------------------------------------------------
def git(*args: str, cwd: Path = REPO, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def fetch_tags() -> None:
    """`stable` is force-moved, so a plain fetch leaves a stale local tag."""
    git("fetch", "--quiet", "--tags", "--force", "origin")


def remote_ref_sha(ref: str = "stable") -> str:
    """The commit a remote tag/branch points at (peeled for annotated tags)."""
    out = git("ls-remote", "origin", f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}", f"refs/heads/{ref}")
    shas = dict(reversed(line.split("\t")) for line in out.splitlines() if line)
    for key in (f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}", f"refs/heads/{ref}"):
        if key in shas:
            return shas[key]
    raise RuntimeError(f"origin has no ref named {ref!r}")


def show(sha: str, path: str) -> str | None:
    try:
        return git("show", f"{sha}:{path}")
    except RuntimeError:
        return None


def adapter_version(sha: str) -> str | None:
    text = show(sha, "pyproject.toml")
    match = text and re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else None


def adapter_accepts(sha: str, registry: dict) -> tuple[bool, str]:
    """Can the adapter at `sha` parse `registry`? Checked on the `kind` Literal,
    the one field that has broken older adapters (0.4.0 made it tolerant)."""
    types_py = show(sha, "src/ai_model_registry/types.py")
    if types_py is None:
        return False, "commit not found locally (run a fetch)"
    if re.search(r"kind:\s*Kind\s*\|\s*str", types_py):
        return True, "tolerates unknown kinds"
    match = re.search(r"^Kind\s*=\s*Literal\[([^\]]*)\]", types_py, re.M)
    known = set(re.findall(r'"([^"]+)"', match.group(1))) if match else set()
    used = {m.get("kind", "chat") for m in registry.get("models", [])}
    unknown = sorted(used - known)
    if unknown:
        return False, f"rejects kind {', '.join(unknown)}"
    return True, "knows every kind"


def lagging(consumers: list[Consumer], registry: dict) -> list[tuple[Consumer, str, str]]:
    """Consumers whose *committed* pin cannot parse `registry`: (consumer, sha, why).
    Uncommitted pin edits don't count — they are not what any deploy runs."""
    out = []
    for consumer in consumers:
        for sha in shas_of(consumer_pins(consumer, committed=True)):
            ok, why = adapter_accepts(sha, registry)
            if not ok:
                out.append((consumer, sha, why))
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_status(_: argparse.Namespace) -> int:
    fetch_tags()
    stable = remote_ref_sha("stable")
    stable_registry = json.loads(show(stable, "registry.json") or "{}")
    print(f"stable = {stable[:10]} (adapter {adapter_version(stable)})\n")
    bad = 0
    for consumer in load_consumers():
        if not consumer.root.exists():
            print(f"{consumer.name:26} MISSING  {consumer.root}")
            bad += 1
            continue
        pins = consumer_pins(consumer, committed=True)
        shas = shas_of(pins)
        if not shas:
            print(f"{consumer.name:26} no committed pin found in {', '.join(consumer.pin_files)}")
            bad += 1
            continue
        for sha in shas:
            ok, why = adapter_accepts(sha, stable_registry)
            mark = "=" if sha == stable else ("ok" if ok else "!!")
            bad += not ok
            print(f"{consumer.name:26} {mark:2} {sha[:10]}  adapter {adapter_version(sha) or '?':8} {why}")
        if len(shas) > 1:
            print(f"{'':26}    committed pin files disagree: {pins}")
        working = shas_of(consumer_pins(consumer))
        if working != shas:
            print(f"{'':26}    uncommitted edit -> {', '.join(s[:10] for s in working)} (not counted until committed)")
        elif unpushed(consumer):
            print(f"{'':26}    committed but not pushed")
    if bad:
        print(f"\n{bad} consumer(s) cannot read `stable` at their committed pin — run scripts/update_consumers.py, then commit + deploy")
    return 1 if bad else 0


def discover(root: Path) -> dict[str, list[str]]:
    """{repo dir: [pin files]} for every git repo under `root` that pins the registry."""
    found: dict[str, list[str]] = {}
    for name in PIN_FILE_NAMES:
        for file in root.rglob(name):
            if any(part in SKIP_DIRS for part in file.relative_to(root).parts):
                continue
            if file.resolve().is_relative_to(REPO) or not read_pins(file.read_text(errors="ignore")):
                continue
            repo = next((p for p in file.parents if (p / ".git").exists()), None)
            if repo is not None:
                found.setdefault(str(repo), []).append(str(file.relative_to(repo)))
    return found


def cmd_discover(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    found = discover(root)
    known = {c.root for c in load_consumers()} if CONSUMERS_PATH.exists() else set()
    new = {repo: files for repo, files in found.items() if Path(repo) not in known}
    for repo, files in sorted(found.items()):
        print(f"{'new  ' if repo in new else 'known'} {repo}: {', '.join(sorted(files))}")
    if args.write and new:
        data = json.loads(CONSUMERS_PATH.read_text()) if CONSUMERS_PATH.exists() else {"consumers": []}
        for repo, files in sorted(new.items()):
            data["consumers"].append({
                "name": Path(repo).name,
                "path": os.path.relpath(repo, REPO),
                "pin_files": sorted(files),
                "snapshot": None,
                "python": "venv/bin/python",
                "test_cwd": ".",
                "test": ["-m", "pytest", "-q"],
                "followups": ["TODO: check snapshot/python/test in this repo's docs"],
            })
        CONSUMERS_PATH.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\nadded {len(new)} repo(s) to {CONSUMERS_PATH.name} — review snapshot/python/test")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="pin + adapter compatibility per consumer").set_defaults(func=cmd_status)
    p = sub.add_parser("discover", help="scan for repos that pin this package")
    p.add_argument("--root", default=str(REPO.parent), help="directory to scan (default: parent of this repo)")
    p.add_argument("--write", action="store_true", help="append new repos to consumers.json")
    p.set_defaults(func=cmd_discover)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
