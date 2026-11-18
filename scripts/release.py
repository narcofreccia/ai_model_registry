#!/usr/bin/env python3
"""Tag a version and promote it to `stable` (the tag consumers read).

    python3 scripts/release.py --dry-run     # every check, prints the publish commands
    python3 scripts/release.py               # tag v<version>, push, run the promote job, verify

Steps, each one stopping the release on failure:
  1. preflight  on main, clean tree, not behind origin/main, versions agree,
                tag v<version> unused, CHANGELOG top section is v<version> and dated
  2. checks     scripts/validate.py + pytest
  3. impact     what changes for ids consumers already store, vs `stable`: status changes,
                ids now CALLED as another model (resolve_usable), ids whose full chain moved
                (resolve_migration, i.e. get_price). Informational, never stops the release.
  4. consumers  refuse if this release would newly break a repo in consumers.json: its
                *committed* pin reads the current `stable` but not this registry
                (uncommitted pin edits don't count; override: --force-lagging-consumers).
                Repos that are already broken are listed, not blocking.
  5. contract   run each consumer's `contract_test` (its WORKING TREE, its venv) with
                AI_MODEL_REGISTRY_FILE pointing at this registry.json; any failure stops the
                release, dry run included (override: --skip-contract-tests). Consumers with no
                contract_test, or whose adapter predates the override, are listed, not blocking.
  6. review     print the active models per provider and ask for confirmation that the
                deprecation review is done (skip the prompt: --yes)
  7. publish    annotated tag, push main + tag, `gh workflow run ci.yml -f promote=true`,
                watch the run
  8. verify     remote `stable` == HEAD and the raw URL serves this registry
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict

import impact  # puts this repo's src/ on sys.path
from ai_model_registry import OVERRIDE_ENV
from consumers import (
    CONSUMERS_PATH,
    RAW_URL,
    REPO,
    Consumer,
    adapter_accepts,
    fetch_tags,
    git,
    lagging,
    load_consumers,
    remote_ref_sha,
    show,
)

PYTHON = REPO / ".venv" / "bin" / "python"
CONTRACT_TIMEOUT_SECONDS = 300
# exit 0: the installed adapter knows the override; 3: it predates it
SUPPORTS_OVERRIDE = "import sys, ai_model_registry as m; sys.exit(0 if hasattr(m, 'OVERRIDE_ENV') else 3)"


def step(title: str) -> None:
    print(f"\n== {title}")


def die(message: str) -> None:
    sys.exit(f"\nrelease stopped: {message}")


def run(cmd: list[str], dry_run: bool = False) -> None:
    print("   $ " + " ".join(cmd))
    if not dry_run and subprocess.run(cmd, cwd=REPO).returncode != 0:
        die(f"`{' '.join(cmd)}` failed")


def project_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (REPO / "pyproject.toml").read_text(), re.M)
    return match.group(1) if match else die("no version in pyproject.toml")


def package_version() -> str:
    text = (REPO / "src" / "ai_model_registry" / "__init__.py").read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else die("no __version__ in src/ai_model_registry/__init__.py")


def changelog_head() -> str:
    for line in (REPO / "CHANGELOG.md").read_text().splitlines():
        if line.startswith("## "):
            return line
    die("CHANGELOG.md has no `## ` section")


def preflight() -> str:
    step("preflight")
    if git("branch", "--show-current") != "main":
        die("not on main")
    if git("status", "--porcelain"):
        die("working tree is not clean — commit first")
    git("fetch", "--quiet", "origin", "main")
    fetch_tags()
    if git("rev-list", "--count", "HEAD..origin/main") != "0":
        die("main is behind origin/main — pull first")

    version = project_version()
    if package_version() != version:
        die(f"pyproject.toml says {version}, __init__.__version__ says {package_version()}")
    tag = f"v{version}"
    if git("tag", "-l", tag) or git("ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        die(f"tag {tag} already exists — bump the version in pyproject.toml and __init__.py")

    head = changelog_head()
    if tag not in head:
        die(f"CHANGELOG top section does not mention {tag}:\n   {head}")
    if "unreleased" in head.lower() or not re.match(r"## \d{4}-\d{2}-\d{2}", head):
        die(f"CHANGELOG top section is not dated (use `## YYYY-MM-DD — ...`):\n   {head}")

    ahead = git("rev-list", "--count", "origin/main..HEAD")
    print(f"   {tag} at {git('rev-parse', '--short', 'HEAD')}, {ahead} commit(s) to push")
    print(f"   {head}")
    return version


def checks() -> None:
    step("checks")
    python = str(PYTHON) if PYTHON.exists() else sys.executable
    run([python, "scripts/validate.py"])
    run([python, "-m", "pytest", "-q"])


def consumer_gate(registry: dict, force: bool) -> None:
    """Block only consumers this release would *newly* break. One that already cannot
    read the current `stable` is warned about: promoting doesn't make it worse."""
    step("consumers")
    if not CONSUMERS_PATH.exists():
        print("   consumers.json not found — cannot check who would break (see consumers.example.json)")
        return
    behind = lagging(load_consumers(), registry)
    if not behind:
        print("   every consumer's committed pin can read this registry")
        return
    current = json.loads(show(remote_ref_sha("stable"), "registry.json") or "{}")
    newly = []
    for consumer, sha, why in behind:
        already = not adapter_accepts(sha, current)[0]
        print(f"   {'!' if already else '!!'} {consumer.name}: committed pin {sha[:10]} {why}"
              + ("  (already can't read the current `stable`)" if already else ""))
        if not already:
            newly.append(consumer.name)
    if not newly:
        print("   none of them is made worse by this release — fix them with scripts/update_consumers.py,\n"
              "   then commit + deploy each repo")
        return
    if not force:
        die(
            f"{', '.join(newly)} would silently fall back to stale data once this is `stable`.\n"
            "   Bump them first (scripts/update_consumers.py --sha <commit>), then commit + deploy each,\n"
            "   or pass --force-lagging-consumers."
        )
    print("   --force-lagging-consumers: continuing anyway")


def migration_impact() -> None:
    """Informational: what a stored id means under this registry vs `stable`."""
    step("migration impact (vs `stable`)")
    try:
        stable = remote_ref_sha("stable")
        old = impact.parse(show(stable, "registry.json") or "")
        new = impact.parse((REPO / "registry.json").read_text())
    except Exception as exc:  # never blocks: the report is a reading aid
        print(f"   could not compare with `stable`: {exc}")
        return
    print(f"   stable = {stable[:10]}")
    for line in impact.report(impact.compute(old, new)):
        print(f"   {line}")


def override_support(consumer: Consumer) -> str | None:
    """None when the consumer's installed adapter honours AI_MODEL_REGISTRY_FILE, else why not."""
    if not consumer.root.exists():
        return f"repo not found: {consumer.root}"
    if not consumer.python_path.exists():
        return f"python not found: {consumer.python}"
    try:
        result = subprocess.run(
            [str(consumer.python_path), "-c", SUPPORTS_OVERRIDE],
            cwd=consumer.test_dir, capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return f"adapter check failed: {exc}"
    if result.returncode == 3:
        return f"adapter predates {OVERRIDE_ENV}"
    if result.returncode != 0:
        return "cannot import ai_model_registry: " + (result.stderr.strip().splitlines() or ["?"])[-1]
    return None


def run_contract_test(consumer: Consumer, registry_path: str) -> tuple[bool, str]:
    """(passed, combined output) of the consumer's contract_test against `registry_path`."""
    env = {**os.environ, OVERRIDE_ENV: registry_path}
    try:
        result = subprocess.run(
            [str(consumer.python_path), *consumer.contract_test],
            cwd=consumer.test_dir, env=env, capture_output=True, text=True,
            timeout=CONTRACT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {CONTRACT_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def contract_gate(skip: bool) -> None:
    """Run every consumer's contract_test against the candidate registry; any FAIL stops."""
    step("consumer contract tests")
    if not CONSUMERS_PATH.exists():
        print("   consumers.json not found — no contract tests to run")
        return
    consumers = load_consumers()
    untested = [c.name for c in consumers if not c.contract_test]
    gated = [c for c in consumers if c.contract_test]
    if untested:
        print(f"   no contract test: {', '.join(untested)}")
    if not gated:
        return
    if skip:
        print(f"   --skip-contract-tests: not run for {', '.join(c.name for c in gated)}")
        return
    registry_path = str((REPO / "registry.json").resolve())
    print(f"   {OVERRIDE_ENV}={registry_path}")
    print("   each consumer's working tree and venv is what gets tested, not its committed pin")
    failed = []
    for consumer in gated:
        why_not = override_support(consumer)
        if why_not:
            print(f"   -- {consumer.name}: not gated: {why_not}")
            continue
        passed, output = run_contract_test(consumer, registry_path)
        print(f"   {'PASS' if passed else 'FAIL'} {consumer.name}")
        if not passed:
            failed.append(consumer.name)
            print("\n".join("        " + line for line in output.splitlines()[-25:]))
    if failed:
        die(
            f"contract test failed for {', '.join(failed)}: this registry breaks what they serve.\n"
            "   Fix the registry change or the consumer (then deploy it) first,\n"
            "   or pass --skip-contract-tests."
        )


def review(registry: dict, assume_yes: bool) -> None:
    step("deprecation review")
    active: dict[str, list[str]] = defaultdict(list)
    for model in registry["models"]:
        if model["status"] == "active":
            active[model["provider"]].append(f"{model['id']} ({model['kind']})")
    for provider, ids in sorted(active.items()):
        print(f"   {provider:11} {', '.join(ids)}")
    print("   Each of these must still be active on the provider's deprecations page.")
    if assume_yes:
        return
    if input("   Deprecation review done for this release? [y/N] ").strip().lower() != "y":
        die("deprecation review not confirmed")


def find_promote_run(head: str) -> str:
    for _ in range(30):
        out = subprocess.run(
            ["gh", "run", "list", "--workflow=ci.yml", "--branch=main", "--event=workflow_dispatch",
             "--limit=5", "--json", "databaseId,headSha"],
            cwd=REPO, capture_output=True, text=True,
        ).stdout
        for entry in json.loads(out or "[]"):
            if entry["headSha"] == head:
                return str(entry["databaseId"])
        time.sleep(2)
    die("the promote run did not show up — check GitHub Actions")


def publish(version: str, dry_run: bool, watch: bool) -> str:
    step("publish" + (" (dry run: nothing below is executed)" if dry_run else ""))
    tag = f"v{version}"
    head = git("rev-parse", "HEAD")
    run(["git", "tag", "-a", tag, "-m", f"ai-model-registry {version}"], dry_run)
    run(["git", "push", "origin", "main", tag], dry_run)
    run(["gh", "workflow", "run", "ci.yml", "--ref", "main", "-f", "promote=true"], dry_run)
    if dry_run:
        print("   $ gh run watch <promote run id> --exit-status")
    elif watch:
        run(["gh", "run", "watch", find_promote_run(head), "--exit-status"])
    return head


def verify(head: str, registry: dict) -> None:
    step("verify")
    for _ in range(10):
        stable = remote_ref_sha("stable")
        if stable == head:
            break
        time.sleep(3)
    else:
        die(f"`stable` is at {stable[:10]}, expected {head[:10]} — check the promote run")
    print(f"   stable -> {head}")
    try:
        with urllib.request.urlopen(RAW_URL.format(ref="stable"), timeout=15) as response:
            served = json.loads(response.read())
        same = served.get("generated_at") == registry.get("generated_at")
        print(f"   raw URL generated_at {served.get('generated_at')}" + ("" if same else "  (CDN may lag ~5 min)"))
    except Exception as exc:  # the tag moved; the raw fetch is only a courtesy check
        print(f"   could not fetch the raw URL: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="run every check, execute nothing that publishes")
    parser.add_argument("--yes", action="store_true", help="skip the deprecation-review prompt")
    parser.add_argument("--skip-watch", action="store_true", help="do not wait for the promote run")
    parser.add_argument("--force-lagging-consumers", action="store_true", help="promote even if a consumer cannot read it")
    parser.add_argument("--skip-contract-tests", action="store_true", help="do not run the consumers' contract tests")
    args = parser.parse_args()

    version = preflight()
    checks()
    registry = json.loads((REPO / "registry.json").read_text())
    migration_impact()
    consumer_gate(registry, args.force_lagging_consumers)
    contract_gate(args.skip_contract_tests)
    review(registry, args.yes or args.dry_run)
    head = publish(version, args.dry_run, not args.skip_watch)
    if args.dry_run:
        print("\ndry run finished: all checks passed")
        return 0
    if args.skip_watch:
        print("\npromote run started; verify later with: python3 scripts/consumers.py status")
        return 0
    verify(head, registry)
    print(f"\nreleased v{version}. Next: python3 scripts/update_consumers.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
