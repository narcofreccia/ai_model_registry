---
name: update-ai-registry-consumers
description: Bump the ai-model-registry pin (and vendored snapshot) in every linked repo listed in consumers.json, reinstall and run their tests. Edits only — never commits or pushes. Use after a release, or when `scripts/consumers.py status` shows a repo that cannot read `stable`.
---

# Update the registry pin in consumer repos

The repos live in `consumers.json` (gitignored; shape in `consumers.example.json`).
If it is missing, run `python3 scripts/consumers.py discover --write` and fill in each
new entry's `snapshot` / `python` / `test` from that repo's `docs/ai_model_registry.md`.

## Steps

1. `.venv/bin/python scripts/consumers.py status`: current pin per repo, and whether its
   adapter can read `stable`.
2. `.venv/bin/python scripts/update_consumers.py --dry-run`: which files will change.
   The default target is the commit `stable` points at; `--sha <sha>` picks another
   (it must be pushed); `--only a,b` narrows the run.
3. `.venv/bin/python scripts/update_consumers.py --verify`: rewrites the pins, overwrites
   vendored snapshots with that commit's `registry.json` (pin and snapshot always move
   together), force-reinstalls the pin into each repo's venv, and runs its tests. Large
   suites take minutes, so run it in the background.
4. For every failing repo, read the failure. If it comes from the registry change (a
   hard-coded model count, a model id that moved to `deprecated`, a catalog-order test),
   propose the fix and ask before editing that repo. Otherwise report it as pre-existing:
   check with `git stash` only if the user agrees.
5. Report a table: repo, old → new SHA, files touched, tests, and the `followups` from
   consumers.json (Heroku push, docker rebuild...).

## Never

- Commit, push, or deploy in a consumer repo. The user does that after review.
- Discard or overwrite the repos' unrelated uncommitted work. The script only touches pin files and snapshots.
