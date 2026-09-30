#!/usr/bin/env python3
"""Move every consumer's ai-model-registry pin to one commit. Edits files only:
nothing is committed or pushed — review and commit in each repo yourself.

    python3 scripts/update_consumers.py --dry-run          # show what would change
    python3 scripts/update_consumers.py                    # pin -> commit `stable` points at
    python3 scripts/update_consumers.py --verify           # ...then reinstall + run each test suite
    python3 scripts/update_consumers.py --sha <sha> --only tide_reel,tide_share

Per consumer (see consumers.json): rewrite the pin in every `pin_files` entry and, when
the repo vendors a `snapshot`, overwrite it with that commit's registry.json — pin and
snapshot move together, never one without the other.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

from consumers import (
    GIT_URL,
    RAW_URL,
    Consumer,
    adapter_accepts,
    adapter_version,
    consumer_pins,
    fetch_tags,
    git,
    load_consumers,
    remote_ref_sha,
    rewrite_pins,
    show,
)


def resolve_target(args: argparse.Namespace) -> str:
    fetch_tags()
    if args.sha:
        full = git("rev-parse", "--verify", f"{args.sha}^{{commit}}")
        if git("branch", "-r", "--contains", full) == "":
            sys.exit(f"{full[:10]} is not on any remote branch — push it first")
        return full
    return remote_ref_sha(args.ref)


def fetch_registry(sha: str) -> bytes:
    """The exact bytes consumers would download for this commit."""
    with urllib.request.urlopen(RAW_URL.format(ref=sha), timeout=15) as response:
        body = response.read()
    json.loads(body)  # refuse to vendor a non-JSON error page
    return body


def is_dirty(consumer: Consumer) -> bool:
    return git("status", "--porcelain", cwd=consumer.root, check=False) != ""


def update(consumer: Consumer, sha: str, registry_bytes: bytes, dry_run: bool) -> list[str]:
    touched = []
    for rel in consumer.pin_files:
        file = consumer.root / rel
        text = file.read_text()
        new_text, count = rewrite_pins(text, sha)
        if count == 0:
            print(f"    !! no pin found in {rel}")
        elif new_text != text:
            touched.append(rel)
            if not dry_run:
                file.write_text(new_text)
    if consumer.snapshot:
        file = consumer.root / consumer.snapshot
        if not file.exists() or file.read_bytes() != registry_bytes:
            touched.append(consumer.snapshot)
            if not dry_run:
                file.write_bytes(registry_bytes)
    return touched


def verify(consumer: Consumer, sha: str) -> bool:
    python = consumer.root / consumer.python
    if not python.exists():
        print(f"    !! {consumer.python} not found — skipping install + tests")
        return False
    pin = f"ai-model-registry @ git+{GIT_URL}@{sha}"
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "--force-reinstall", "--no-deps", pin],
        cwd=consumer.root, capture_output=True, text=True,
    )
    if install.returncode != 0:
        print(f"    !! pip install failed:\n{install.stderr[-2000:]}")
        return False
    tests = subprocess.run(
        [str(python), *consumer.test],
        cwd=consumer.root / consumer.test_cwd, capture_output=True, text=True,
    )
    tail = (tests.stdout or tests.stderr).strip().splitlines()[-1:] or ["(no output)"]
    print(f"    tests: {'PASS' if tests.returncode == 0 else 'FAIL'} — {tail[0]}")
    if tests.returncode != 0:
        print("\n".join("      " + line for line in tests.stdout.strip().splitlines()[-25:]))
    return tests.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--sha", help="commit to pin (must be pushed)")
    target.add_argument("--ref", default="stable", help="remote tag/branch to resolve (default: stable)")
    parser.add_argument("--only", help="comma-separated consumer names")
    parser.add_argument("--verify", action="store_true", help="reinstall the pin and run each repo's tests")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    args = parser.parse_args()

    consumers = load_consumers()
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {c.name for c in consumers}
        if unknown:
            sys.exit(f"unknown consumer(s): {', '.join(sorted(unknown))}")
        consumers = [c for c in consumers if c.name in wanted]

    sha = resolve_target(args)
    registry_text = show(sha, "registry.json")
    ok, why = adapter_accepts(sha, json.loads(registry_text or "{}"))
    print(f"target {sha} (adapter {adapter_version(sha)}){'  [dry run]' if args.dry_run else ''}\n")
    if not ok:
        sys.exit(f"the adapter at {sha[:10]} cannot read its own registry.json ({why})")
    needs_snapshot = any(c.snapshot for c in consumers)
    registry_bytes = fetch_registry(sha) if needs_snapshot else b""

    results = []
    for consumer in consumers:
        print(f"== {consumer.name}  ({consumer.root})")
        if not consumer.root.exists():
            print("    !! repo not found")
            results.append((consumer, "missing", None))
            continue
        before = sorted({s for pins in consumer_pins(consumer).values() for s in pins})
        if is_dirty(consumer):
            print("    note: working tree has uncommitted changes (left as they are)")
        touched = update(consumer, sha, registry_bytes, args.dry_run)
        old = ", ".join(s[:10] for s in before) or "none"
        print(f"    {old} -> {sha[:10]}: " + (", ".join(touched) if touched else "already up to date"))
        passed = verify(consumer, sha) if args.verify and not args.dry_run else None
        for followup in consumer.followups:
            print(f"    follow-up: {followup}")
        results.append((consumer, "changed" if touched else "same", passed))

    print("\nsummary")
    for consumer, state, passed in results:
        tests = {True: "tests pass", False: "TESTS FAIL", None: ""}[passed]
        print(f"  {consumer.name:26} {state:8} {tests}")
    if not args.dry_run and any(s == "changed" for _, s, _ in results):
        print("\nNothing was committed. In each changed repo: review `git diff`, commit, deploy.")
    return 1 if any(p is False or s == "missing" for _, s, p in results) else 0


if __name__ == "__main__":
    sys.exit(main())
