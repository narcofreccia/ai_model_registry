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

1. Merge to `main` with CI green.
2. Add the `CHANGELOG.md` entry for the promotion (date + what changed).
3. Trigger the promote run. Either GitHub → Actions → **CI** → *Run workflow* →
   `promote: true`, or from the CLI:

   ```bash
   gh workflow run ci.yml --ref main -f promote=true
   gh run watch "$(gh run list --workflow=ci.yml --branch=main --limit=1 --json databaseId --jq '.[0].databaseId')"
   ```

   The job re-runs validation and only then force-moves the tag.
4. Verify: `curl -s https://raw.githubusercontent.com/narcofreccia/ai_model_registry/stable/registry.json | head`.

Consumers pinning a SHA (tide_share's desktop builds) are unaffected until they bump it.
