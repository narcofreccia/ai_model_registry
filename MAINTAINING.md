# Maintaining the registry

Everything here edits **`registry.json` at the repo root**. It is the only source of truth;
the wheel copies it in at build time, so there is no second file to keep in sync.

Before every push: `python3 scripts/validate.py` (green = no failures).

## Add a model

1. Append to `models` — **all fields are required** (use `null` / `false` / `[]`, never omit):
   `id`, `name`, `description`, `provider`, `kind`, `api_model_id`, `aliases`,
   `reasoning`, `allows_temperature`, `responses_api`, `server_web_tools`, `vision`,
   `needs_pdf_rasterization`, `max_reference_images`, `voices`, `status`, `pricing`.
   `modalities` is optional (realtime models only; `null` elsewhere). The decision fields
   (`question_types`, `max_request_tokens`, `max_state_question_tokens`,
   `max_choice_options`, `max_score_levels`) are optional and decision-only.
2. `provider` must be a key in `providers`; add the provider first if it's new.
3. `id` is what consumers store. `api_model_id` is what goes on the wire (differs for
   dated snapshot ids). Old names for the *same* model go in `aliases`; names of a
   *superseded* model go in `migrations` instead.
4. Position matters: active chat models are kept in tide_share's catalog order — append
   new ones after the existing active block, before the deprecated entries.
5. Pricing: copy a figure only from a provider price page or a source repo that states it.
   **Never estimate, never interpolate from a sibling model.** No verified number →
   `"pricing": null` plus a TODO line in `CHANGELOG.md`.
6. `python3 scripts/validate.py`, commit, note it in `CHANGELOG.md`.

## Change a price

- Edit the **base** rate in place (`input_per_1m` / `output_per_1m` / `cached_input_per_1m`,
  or `per_image`). Do not keep the old number anywhere — git history is the audit trail.
- Set `"effective_from": "YYYY-MM-DD"` when you know the date the new rate started.
- A *conditional* rate (off-peak, batch, long-context, quality tier) is not a base price:
  add it to `pricing.variants` as `{"condition": "...", <rate keys>, "note": "..."}`.
  Conditions are an open vocabulary; consumers ignore ones they don't know.
- A cached-input rate that always applies belongs in base `cached_input_per_1m`, not a variant.

## Add a realtime model

`kind: "realtime"` (speech-to-speech / audio models). On top of the fields above:

1. `voices` must be a **non-empty** list — validation fails otherwise; copy the provider's
   voice set verbatim (OpenAI's 12, Google Live's 30).
2. `modalities` = the session modality tokens spelled as the API wants them:
   `["text","audio"]` for OpenAI realtime, `["AUDIO"]` for Google Live.
3. Pricing uses the **realtime shape** — `audio_input_per_1m`, `audio_output_per_1m`,
   `text_input_per_1m`, `text_output_per_1m`, `cached_input_per_1m` (all USD per 1M
   tokens), plus `cached_audio_input_per_1m` only when the provider prices cached audio
   apart from cached text. Mixing in `input_per_1m` / `per_image` fails validation, and so
   does putting the audio/text keys on a non-realtime model. A rate the provider does not
   publish is `null` — never derived from a sibling model.
4. Preview-dated ids (`…-preview-09-2025`) churn: when a newer date lands, deprecate the
   old id and add the migration rather than editing it in place.

## Add a decision model

`kind: "decision"` (structured-decision models such as TypeSafe Jev: typed questions in,
probabilities out, no text). On top of the common fields:

1. `question_types` must be a **non-empty** list of the provider's question type tokens,
   spelled as the API wants them (TypeSafe `["noul","choice","score"]`) — validation
   fails otherwise.
2. Copy the provider's published limits into `max_request_tokens`,
   `max_state_question_tokens`, `max_choice_options`, `max_score_levels`; `null` when
   not published. These fields on any other kind fail validation.
3. Pricing uses the **token shape**. Input-only billing is `"output_per_1m": 0`, which
   is a published fact, not a missing one (`pricing: null` still means unverified).
4. `reasoning: "none"`; `allows_temperature: false` when the model has no sampling
   parameters, even if the API ignores rather than rejects them.
5. New decision models go after the existing decision block at the end of `models`.

## Add an image model

`kind: "image_gen"`. On top of the common fields:

1. `max_reference_images` = the provider's total reference/input image limit.
2. `image_sizes` / `default_image_size` / `aspect_ratios` (schema_minor 3): copy the
   provider's per-model lists verbatim, spelled as the API wants them (`"512"`, `"1K"` —
   uppercase K). A list the provider doesn't publish for *this* model is `null`, never
   borrowed from a sibling. `default_image_size` must be one of `image_sizes`.
3. Pricing: `per_image` = the price at `default_image_size`; every other size is an
   `image_size_<token>` variant (`image_size_512`, `image_size_2k`, `image_size_4k`).
   Token-billed models with no published per-image figure stay `null` + a CHANGELOG note.
4. New image models go after the existing active image block.

## Extend the schema

Additive changes (a new kind, a new optional field, a new pricing shape) bump
**`schema_minor`**, not `schema_version`. `schema_version` is the MAJOR and moves only for
a change that stops older consumers loading the file. `schema_minor` is a separate integer
key precisely so adapters that type `schema_version` as an `int` keep working — never turn
`schema_version` into a fractional number. Before promoting an additive change, load the
new `registry.json` through the **`stable`** adapter and confirm the older kinds' output is
byte-identical. A new `kind` value is the exception: adapters before 0.4.0 reject an
unknown kind outright, so do not promote a registry carrying one until every consumer
pins adapter 0.4.0+.
- One `CHANGELOG.md` line per price change: model, old → new, source.

## Deprecate or retire a model

1. Set `"status": "deprecated"` (still callable) or `"retired"` (gone from the provider).
   Keep the entry — deleting it breaks every consumer with that id saved.
2. **Mandatory**: add `"<old-id>": "<successor-id>"` to `migrations`. Validation fails
   without it, and again if the chain doesn't end at a real model id.
3. Chains are fine (`gpt-4o` → `gpt-5.4` → `gpt-5.6-terra`); cycles fail validation.
4. Removing an id entirely is only allowed with a migration entry left behind —
   `validate.py` diffs against `stable` and rejects a silent removal.

The adapter reads a chain two ways:

- `resolve_migration(id)` (and `resolve`, `get_price`, `price_for`) follows the chain to its
  end, whatever the status of the hops: the **latest successor**.
- `resolve_usable(id)` (and `usable`) is what an app should **call**: an active or
  deprecated id comes back as given; a retired or unknown id steps along the chain and stops
  at the first model that is not retired.

So a status change that turns a model into a non-terminal hop (deprecating it adds its own
migration) moves every older id that pointed at it: their full chain now ends at the new
successor, and any consumer that resolves with `resolve_migration`, or prices with
`get_price`, lands on a model it may have no setup for. That is how v0.5.3 broke three
consumers that read `stable` at runtime. Before promoting such a change, read the
**migration impact** step of `release.py --dry-run` and make sure every consumer can serve
each new target (its contract test passes, below).

## Validate locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/validate.py     # schema, uniqueness, providers, migrations,
                                         # lifecycle, and the diff vs `stable`
.venv/bin/python -m pytest               # adapter behavior
```

Checks enforced: schema-valid; unique `id`/`aliases`/`api_model_id` (aliases may not
collide with ids); every `provider` exists; every migration chain terminates at a real
model id; every deprecated/retired model has a migration; no model removed since `stable`
without one.

## Promote to `stable`

Consumers read the `stable` tag, so a merge to `main` changes nothing until promotion.
In Claude Code, `/release-ai-registry` runs the whole thing, deprecation review included.

1. Deprecation review: check every `active` id against the provider deprecations pages
   (see `.claude/skills/release-ai-registry/SKILL.md` for the URLs) and apply what changed.
2. Bump `version` in `pyproject.toml` and `__version__` in `src/ai_model_registry/__init__.py`.
3. Date the top `CHANGELOG.md` section with the promotion date and name the version:
   `## YYYY-MM-DD — summary (v0.4.0 → v0.4.1, ...)`. Commit on `main`.
4. Release:

   ```bash
   .venv/bin/python scripts/release.py --dry-run   # checks only, prints the publish commands
   .venv/bin/python scripts/release.py             # tag v<version>, push, promote, verify
   ```

   It checks, in order: on main, clean, not behind origin; versions agree; the tag is
   unused; the CHANGELOG is dated; validate + pytest. It prints the **migration impact**
   against `stable` (status changes; ids an app would now *call* as another model; ids whose
   full chain, and so `get_price`, moved). That report never blocks; read it. Then:
   **the release newly breaks no consumer in `consumers.json`**: judged on each repo's
   *committed* pin, so an uncommitted bump doesn't count, and repos that already can't read
   the current `stable` are listed without blocking (`--force-lagging-consumers` overrides).
   Then the **contract gate**: every consumer with a `contract_test` runs it from its own
   working tree and venv with `AI_MODEL_REGISTRY_FILE` set to this `registry.json`; one
   failure stops the release, dry run included (`--skip-contract-tests` skips the step, only
   when the user accepts the risk). A consumer whose installed adapter predates
   `AI_MODEL_REGISTRY_FILE` (0.6.0) is listed as not gated, as is one with no
   `contract_test`. Then it tags, pushes, runs
   `gh workflow run ci.yml -f promote=true`, watches it, and checks that `stable` moved.
   The CI job re-validates before it force-moves the tag.
5. Move the consumers to the new commit: `scripts/update_consumers.py --verify` (below) runs
   each repo's `registry_test`, or its full `test` where none is defined; `--full` forces the
   full suite.

Consumers pinning a SHA (tide_share's desktop builds) are unaffected until they bump it.

## Consumers

`consumers.json` (gitignored, machine-specific paths; shape in `consumers.example.json`)
lists every repo that pins this package, with its pin files, vendored snapshot, venv
python and test command. Two optional fields, each run as `<python> <args...>` from
`test_cwd` like `test`:

- `contract_test`: a fast invariant test the release gate runs against the **candidate**
  registry (below). A repo without one is not gated.
- `registry_test`: a fast subset of the repo's suite covering its registry integration;
  `update_consumers.py --verify` runs it instead of the full `test`.

`AI_MODEL_REGISTRY_FILE=<path>` makes every `load()` (adapter 0.6.0+) read exactly that file:
no fetch, no cache read or write, no fallback; a missing or invalid file raises. Use it to
run any consumer against a candidate registry by hand.

```bash
.venv/bin/python scripts/consumers.py status              # pin + adapter per repo; can it read `stable`? gated?
.venv/bin/python scripts/consumers.py discover --write    # pick up repos that started pinning us
.venv/bin/python scripts/update_consumers.py --dry-run    # pin -> commit `stable` points at
.venv/bin/python scripts/update_consumers.py --verify     # ...rewrite, reinstall, run registry_test (else test)
.venv/bin/python scripts/update_consumers.py --verify --full   # ...run the full `test` everywhere
.venv/bin/python scripts/impact.py --old v0.5.4           # the release's impact report vs any ref
```

`update_consumers.py` only edits files: the pin line(s) and, where one is vendored, the
snapshot, which always moves with the pin. Committing and deploying each repo is manual.
In Claude Code: `/update-ai-registry-consumers`.

### Writing a consumer contract test

The gate runs it against registries **newer than the app's pin**, so it asserts invariants,
never counts, catalog order or "this exact list of models". For every model id the app has
stored defaults for, or local per-model setup for (a mapping, a size table, a prompt),
assert that `registry.resolve_usable(id)` lands on a model the app can serve, and that no
default model is `retired`. Load the registry the way the app does (`load(...)`), so the
override decides the data; keep it to seconds, with no network and no database.
