---
name: release-ai-registry
description: Publish ai_model_registry — deprecation review against provider pages, version + CHANGELOG check, then scripts/release.py (tag v<version>, push, CI promote to `stable`, verify). Use when the user says release, publish, tag, promote, or "make it stable".
---

# Release ai_model_registry

`stable` is what every consumer reads, so a release is: review, then `scripts/release.py`.
The script does the mechanical part and refuses unsafe states. Your job is the judgment
before it. Rules for editing `registry.json` live in MAINTAINING.md; follow them.

## 1. Deprecation review (do this every release, before touching the script)

1. List the active models per provider:
   `.venv/bin/python -c "import json;[print(m['provider'],m['id']) for m in json.load(open('registry.json'))['models'] if m['status']=='active']"`
2. Check each provider's **own** deprecations and models pages (WebFetch; delegate to a
   subagent when there are several providers):
   - OpenAI: developers.openai.com/api/docs/deprecations, /api/docs/models
   - Anthropic: platform.claude.com/docs/en/about-claude/model-deprecations, /models/overview
   - Google: ai.google.dev/gemini-api/docs/deprecations
   - OpenRouter slugs: `https://openrouter.ai/api/v1/models/<slug>/endpoints` (404 = gone)
3. Propose the changes to the user **before** editing. Formally deprecated → `deprecated`;
   shut down → `retired`. Either way add a `migrations` entry to the provider's named
   replacement; add that replacement first if it is missing, priced only from the provider
   page, else `pricing: null` + a CHANGELOG TODO. "Legacy" or "superseded" without a
   deprecation notice is a CHANGELOG note, not a status change.
4. Apply the edits, then run `.venv/bin/python scripts/validate.py` and `.venv/bin/python -m pytest`.
   `tests/test_accessors.py` pins the active chat order and the per-kind counts, so update it with the change.

## 2. Version + CHANGELOG

- Bump `version` in `pyproject.toml` **and** `__version__` in `src/ai_model_registry/__init__.py`.
  Registry-only changes are a patch bump; adapter/schema changes follow MAINTAINING.md "Extend the schema".
- The top CHANGELOG section must be `## <today's date> — <summary> (v<old> → v<new>, ...)`.
  Dates are promotion dates, so set it to the day you run the release.
- Commit on main (the user decides the message; end with the attribution line).

## 3. Run the script

```bash
.venv/bin/python scripts/release.py --dry-run   # all checks, prints the publish commands
.venv/bin/python scripts/release.py --yes       # after the user confirms; --yes = review done
```

It stops on any of the following. Fix the cause; don't work around it:
- not on main, a dirty tree, or behind origin
- the two version strings disagree
- tag `v<version>` already exists
- the CHANGELOG head is undated
- validate or pytest fails
- **the release would newly break a consumer:** its *committed* pin (HEAD, not the working
  tree) can read the current `stable` but not this registry. Bump those consumers first
  (`/update-ai-registry-consumers` with the last compatible SHA), then have the user commit
  and deploy them. Pass `--force-lagging-consumers` only if the user explicitly accepts
  that they fall back to stale data. Consumers that already can't read the current `stable`
  are listed, not blocking: tell the user, since they need a bump + deploy either way.

Pushing and promoting are outward-facing: always show the dry-run output and get a yes first.

## 4. After

`scripts/release.py` prints the promoted SHA. Offer `/update-ai-registry-consumers` to move every
linked repo to it.
