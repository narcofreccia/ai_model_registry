# Changelog

Dates are the promotion date (when `stable` was moved), not the merge date.

## Unreleased — `server_web_tools` audited for OpenAI + Z.ai (facts only, no schema change)

`server_web_tools` was `false` on every non-Anthropic chat model even though OpenAI's
Responses API exposes the built-in `web_search` tool and Z.ai exposes a server-side
`web_search` tool. Now `true` on: gpt-5.6-sol / -terra / -luna, gpt-5.5, gpt-5.4 (+mini,
+nano), gpt-5.3, gpt-5.2, gpt-5.1, gpt-5 (+mini, +nano), o3, o4-mini, gpt-4.1 (+mini)
— per OpenAI's web-search guide (Responses `web_search`; the 4o family only had it via the
retired `*-search-preview` variants, so 4o stays `false`; pro variants left `false` pending
verification) — and glm-5.3-flash (Z.ai `tools: [{type: "web_search"}]`, a different wire
shape than OpenAI's, noted in its description). Consumers that need the OpenAI shape must
still check `responses_api` alongside this flag. Sources: developers.openai.com
tools-web-search guide + pricing (reasoning models $10/1k calls + content tokens;
non-reasoning $25/1k calls), docs.z.ai guides/tools/web-search.

## 2026-08-30 — the `realtime` kind (v0.3.0, schema 1.1)

73 models (50 chat, 5 embedding, 8 image_gen, **10 realtime**), 66 migrations, 6 providers.
Additive only: no existing model's facts changed, and `models_by_kind("chat")`,
`("embedding")` and `("image_gen")` are byte-identical to the previous `stable`.

**Why** — tide-voice-agent's model facts were quadruplicated (its `model_factory.py`
defaults + voice sets, its admin dropdown, its usage tracker's fallback pair, and
tide_backend's 10 "registry-excluded" realtime pricing literals). Registry-excluded is no
longer true: realtime models now live here like every other kind.

**Schema — additive, `schema_minor: 1`**

- `kind` gains `"realtime"` (the enum already listed it; nothing used it).
- New `pricing` shape `realtime_pricing`: `audio_input_per_1m`, `audio_output_per_1m`,
  `text_input_per_1m`, `text_output_per_1m`, `cached_input_per_1m`, plus optional
  `cached_audio_input_per_1m`. USD per 1M tokens, like every other rate here. Audio and
  text bill on separate axes, so the chat shape cannot express these models.
- New optional model field `modalities` (session modality tokens, spelled as the provider
  wants them). `voices` already existed and is now mandatory-non-empty for realtime.
- New optional top-level `schema_minor` — the MINOR counter for additive changes.
  `schema_version` stays the MAJOR integer `1` **on purpose**: adapters (this one included)
  type it as `int`, so a fractional `1.1` would have stopped every already-pinned consumer
  from loading a refreshed snapshot. Older adapters ignore `schema_minor` and `modalities`
  outright (`extra="ignore"`).

**Adapter** — `Pricing` gains the four realtime rate fields, `cached_audio_input_per_1m`
and an `is_realtime` property; `Model` gains `modalities`; `RegistryData` gains
`schema_minor` (defaults to 0). Every field stays optional, so old snapshots load unchanged
and a consumer reading only the chat axis sees `None`, never an error.

**Added — realtime** (id → migration; rates USD per 1M)

| id | status | audio in/out | text in/out | cached in |
|---|---|---|---|---|
| `gpt-realtime-2.1` | active | 32 / 64 | 4 / 24 | 0.40 |
| `gpt-realtime-2` → `gpt-realtime-2.1` | deprecated | 32 / 64 | 4 / 24 | 0.40 |
| `gpt-realtime-1.5` → `gpt-realtime-2` | deprecated | 32 / 64 | 4 / 16 | 0.40 |
| `gpt-audio-1.5` | active | 32 / 64 | 4 / 16 | 0.40 |
| `gpt-4o-realtime-preview` → `gpt-realtime-2.1` | deprecated | 40 / 80 | 2.50 / 10 | 2.50 |
| `gpt-4o-mini-realtime-preview` → `gpt-realtime-2.1` | deprecated | 10 / 20 | 0.15 / 0.60 | 0.30 |
| `gemini-3.1-flash-live-preview` | active | 3 / 12 | 0.75 / 4.50 | 3 |
| `gemini-live-2.5-flash-native-audio` | active | 3 / 12 | 0.50 / 2 | 3 |
| `gemini-2.5-flash-native-audio-preview-12-2025` | active | 3 / 12 | 0.50 / 2 | 3 |
| `gemini-2.5-flash-native-audio-preview-09-2025` → `-12-2025` | deprecated | 3 / 12 | 0.50 / 2 | 3 |

`gpt-realtime-1.5` migrates through `gpt-realtime-2` to `gpt-realtime-2.1`; both stay
**deprecated, not retired** — house rule: deprecated ids remain callable verbatim.

**Source of the prices** — tide_backend `app/ai_token_ledger/seed_pricing.py`'s realtime
literal rows (`*_usd_per_1m`, verified against the OpenAI and Google pricing pages on the
dates noted in that file), copied 1:1: that file was rescaled to per-1M in migration
`airates1m01`, so it already publishes the unit this registry uses — no conversion. Google
Live has no cache discount (context caching is "Not available" on the Live API); the seeder
sets cached input to the full audio input rate and that is what is recorded here. No rate
the seeder lacks was invented: `cached_audio_input_per_1m` is absent everywhere.

**Voices / modalities** — copied verbatim from tide-voice-agent `agent/model_factory.py`
(OpenAI's 12, Google's 30) and its realtime-session calls (`["text","audio"]` /
`["AUDIO"]`).

**Careful, billers** — `get_price(id)` applies migrations, so it returns the *successor's*
rates for a deprecated id (`get_price("gpt-realtime-1.5")` gives Realtime 2.1's $24 text
output, not its own $16). A biller charging a deprecated id verbatim must read
`registry.get(id).pricing`. Pre-existing behavior, newly consequential now that deprecated
realtime ids stay selectable.

**Validation** — `validate.py` gains the realtime invariants: voices non-empty, pricing on
the realtime axes only, and no audio/text rate keys on a non-realtime model.

## 2026-08-30 — tide_reel coverage (v0.2.1)

63 models (50 chat, 5 embedding, 8 image_gen), 61 migrations, 6 providers. Additive only:
no existing model's facts changed. `schema_version` stays 1.

**Why** — `tide_reel` (TideReel desktop editor) adopted the registry; its hand-written
alias/mapping tables carried 12 ids the registry did not know, which would have made them
resolve as "unknown" and silently reprice/reroute. All 12 are now deprecated entries with
migrations, so every id a TideReel install can hold resolves to a live successor.

**Source** — `tide_reel/tidereel/models.py` (`anthropic_mappings`, `openai_mappings`,
`_LEGACY_REASONING_OPENAI_IDS`, `EMBEDDING_MODELS`) as of `8db34cc`.

**Added — chat** (id → migration)

- `gpt-5.4-pro` → `gpt-5.6-sol` — Responses API, openai_effort
- `gpt-5.3` → `gpt-5.4`, `gpt-5.2` → `gpt-5.4`, `gpt-5.2-pro` → `gpt-5.5` (migrations for
  the last two pre-existed; the model entries did not)
- `o4-mini` → `gpt-5.6-luna` — rejects temperature, Responses API
- `claude-opus-4-7` → `claude-opus-4-8` (adaptive thinking, no temperature)
- `claude-opus-4-5`, `claude-opus-4-1`, `claude-opus-4` → `claude-opus-4-8` (token budget)
- `claude-sonnet-3-7` → `claude-sonnet-5` (api id `claude-3-7-sonnet-20250219`)
- `claude-haiku-3-5` → `claude-haiku-4-5` (api id `claude-3-5-haiku-20241022`, no reasoning)

**Added — embedding**

- `text-embedding-ada-002` → `text-embedding-3-small` (dimension-compatible successor)

**Pricing** — all 12 land unpriced (`pricing: null`). TODO: backfill list prices for the
legacy OpenAI/Anthropic tiers from a provider price page; none was quoted by the source repo.

**Note on dated api ids** — TideReel pins dated snapshot ids for some models
(`gpt-5.1-2025-11-13`, `claude-opus-4-5-20251101`, …). Those stay an app-local policy
overlay in `tidereel/models.py`; the registry keeps the undated canonical `api_model_id`
so other consumers are unaffected.

## 2026-08-29 — tide_backend coverage + price backfill (v0.2.0)

51 models (39 chat, 4 embedding, 8 image_gen), 52 migrations, 6 providers. Additive only:
no existing active model's facts changed. `schema_version` stays 1.

**Why** — `tide_backend` model ids could resolve only partially. Every chat and image id it
can select or has priced now exists in the registry, so a consumer can resolve any stored
`tide_backend` model id to a live successor.

**Sources**

- `tide_backend/app/ai_token_ledger/seed_pricing.py` — the literal `default_pricing` rows.
  Its `*_eur_per_1k` columns are USD **per 1k tokens** despite the name; the `$ … / 1M`
  comments confirm the per-1M figures used here (rate × 1000).
- `tide_backend/app/ai_utils/model_resolver.py` — `DEFAULT_MODEL_BY_OPERATION` (all four
  targets, `gpt-5.4{,-mini,-nano}`, already present and priced).
- `tide_backend/app/fic/autofattura_extraction.py` — `AVAILABLE_MODELS` (all ids were
  already covered as models or migration keys).
- `tide_backend/app/ai_image_gen/clients/{openai_client,google}.py`, `image_router.py` —
  the image ids the clients accept.

**Added — chat** (id → status / migration)

- `gpt-5` → deprecated / `gpt-5.4` — 1.25 / 10
- `gpt-5.1` → deprecated / `gpt-5.4` (migration pre-existed) — 1.25 / 10
- `gpt-5-mini` → deprecated / `gpt-5.4-mini` (migration pre-existed) — 0.25 / 2
- `gpt-5-nano` → deprecated / `gpt-5.4-nano` (migration pre-existed) — 0.05 / 0.40
- `gpt-4` → retired / `gpt-5.6-terra` — 30 / 60
- `gpt-4-turbo` → retired / `gpt-5.6-terra` — 10 / 30
- `gpt-3.5-turbo` → retired / `gpt-5.6-luna` — 0.50 / 1.50
- `o1` → retired / `gpt-5.6-sol` — 15 / 60
- `o1-mini` → retired / `gpt-5.6-luna` — 1.10 / 4.40
- `o3-mini` → retired / `gpt-5.6-luna` — 1.10 / 4.40
- `claude-sonnet-4-5-thinking` → deprecated / `claude-sonnet-5` — pricing `null`, see TODO

`gpt-4` / `gpt-3.5-turbo` / `o1-mini` / `o3-mini` are text-only (`vision: false`); every
retired OpenAI id above is marked `needs_pdf_rasterization: true`. The five retirements
mirror `seed_pricing.py`'s "shutdown 2026-10-23" block (`is_active: False` there).

**Added — image_gen** (all `pricing: null`, see TODO)

- `gpt-image-1` → retired / `openai_gpt_image_2`
- `gpt-image-1-mini` → deprecated / `openai_gpt_image_2` (still callable; active in tide_backend)
- `dall-e-3` → retired / `openai_gpt_image_2` — `max_reference_images: 0`
- `dall-e-2` → retired / `openai_gpt_image_2` — `max_reference_images: 0`

**Aliases** — `nano-banana-pro` on `google_imagen_pro` and `nano-banana` on
`google_imagen_flash`, the bare keys `tide_backend`'s Google client maps to
`gemini-3-pro-image-preview` / `gemini-2.5-flash-image`.

**Price backfill** — 17 → 27 priced. Every new figure comes from a `seed_pricing.py` row;
none was interpolated. No *existing* `null` could be filled: none of the still-unpriced
registry models (`gpt-4.1`, `gpt-4.1-mini`, `claude-opus-4-8`, `claude-opus-4-6`,
`claude-sonnet-4-6`, the Gemini chat models, the OpenRouter models, the embeddings, the
image models) appears in `seed_pricing.py` at all. Rows that *were* already covered agree
with the registry exactly (`gpt-5.5` 5/30 + 0.5 cached, `gpt-5.4` 2.5/15, `gpt-5.4-mini`
0.75/4.5, `gpt-5.4-nano` 0.2/1.25, `gpt-4o` 2.5/10, `gpt-4o-mini` 0.15/0.6, `o3` 2/8,
`claude-sonnet-4-5` and `claude-sonnet-4` 3/15, `claude-haiku-4-5` 1/5) — nothing changed.

TODO — `pricing: null` until a verified figure is found (in addition to the seed-entry list
below, which still stands):

- `claude-sonnet-4-5-thinking`. `seed_pricing.py` carries 6 / 22 for it, but that is
  tide_backend's *blended* internal rate for a thinking run, not an Anthropic list price —
  Anthropic bills extended thinking at Sonnet 4.5's 3 / 15 with reasoning billed as output.
  Recording 6 / 22 as a list price would be wrong, so the field stays `null`.
- All 8 image models. `seed_pricing.py` prices images in internal `fixed_credits`
  (EUR credits incl. margin: 1.50 / 0.32 / 0.45 / 1.50), not USD per image, and its
  `nano-banana-pro` row is a per-token rate (0.002 / 0.012 per 1k) rather than a per-image
  one. Neither maps onto `per_image`.

**Excluded by design** — realtime/audio/video ids stay app-local and are deliberately not
in the registry: `gpt-realtime-{1.5,2,2.1}`, `gpt-audio-1.5`, `gpt-4o{,-mini}-realtime-preview`,
`gemini-3.1-flash-live-preview`, `gemini-live-2.5-flash-native-audio`,
`gemini-2.5-flash-native-audio-preview-{09,12}-2025`, and the commented-out `sora-2{,-pro}`
rows.

## 2026-08-29 — initial seed (schema_version 1)

First `stable`. 36 models (28 chat, 4 embedding, 4 image_gen), 40 migrations, 6 providers.

**Seeded from**

- `tide_share/services/sidecar/tide_share/models.py` — the 21 active models (14 chat,
  4 embedding, 3 image_gen) verbatim and in catalog order, with their capability facts
  (`reasoning`, `allows_temperature`, `responses_api`, `server_web_tools`) and all 27
  `MODEL_MIGRATIONS`; providers from `PROVIDERS` (`key_env` = upper-cased `key_attr`).
- `tide_share/.../image_gen/model_config.py` — image `api_model_id`s
  (`gemini-3-pro-image`, `gemini-3.1-flash-image`, `gpt-image-2`) and
  `max_reference_images` (14 / 3 / 16).
- `ndr_backend/app/fic/autofattura_extraction.py` — its extra chat ids as `deprecated`,
  each with a migration. `needs_pdf_rasterization` mirrors its `_extract_with_openai`
  branch (`model_id.startswith("gpt-5")` ingests PDFs natively): true only for
  `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `o3`.
- `ndr_backend/app/ai_image_gen/model_registry.py` — its image keys folded in as aliases
  (`google/nano-banana-pro`, `gemini-3-pro-image-preview`, `google/nano-banana`,
  `gemini-2.5-flash-image`, `openai/gpt-image-2`); `gpt-image-1.5` added as `retired`
  with `gpt-image-1.5` → `openai_gpt_image_2` (and the same for `openai/gpt-image-1.5`).
- `tide_backend/app/ai_token_ledger/seed_pricing.py` — USD prices from the entries whose
  comments state a per-1M figure.

**Pricing** — 17 models priced, 19 `null`. No number was invented.

Verified: `claude-opus-5` 5/25, `claude-sonnet-5` 2/10, `claude-haiku-4-5` 1/5,
`claude-fable-5` 10/50, `gpt-5.6-sol` 5/30, `gpt-5.6-terra` 2.5/15, `gpt-5.6-luna` 1/6,
`glm-5.3-flash` 0.15/0.50 with 0.03 cached input, `gpt-5.5` 5/30 (0.5 cached),
`gpt-5.4` 2.5/15, `gpt-5.4-mini` 0.75/4.5, `gpt-5.4-nano` 0.2/1.25, `gpt-4o` 2.5/10,
`gpt-4o-mini` 0.15/0.6, `o3` 2/8, `claude-sonnet-4` 3/15, `claude-sonnet-4-5` 3/15.

TODO — `pricing: null` until a verified figure is found:

- Google chat: `gemini-3.1-pro-preview`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`
- OpenRouter: `moonshotai/kimi-k3`, `deepseek/deepseek-v4-pro`, `zai/glm-5.3-flash`
  (incl. any DeepSeek off-peak rate, which belongs in `pricing.variants`)
- All 4 embedding models
- All 4 image_gen models (`seed_pricing.py` carries only internal credit placeholders,
  not USD per-image list prices)
- `gpt-4.1`, `gpt-4.1-mini`, `claude-opus-4-8`, `claude-opus-4-6`, `claude-sonnet-4-6`

**Notes**

- `pricing` gained optional `effective_from` and `variants` (conditional rates keyed by an
  open-vocabulary `condition`). No seeded model uses `variants` yet — nothing verified.
  GLM-5.3-Flash's cached-input rate is an always-on rate, so it sits in base
  `cached_input_per_1m`.
- ndr_backend lists `claude-sonnet-4-5` with `model_id: claude-sonnet-4-5-20250514`, which
  is not the real dated id. The registry uses `claude-sonnet-4-5-20250929` as the
  `api_model_id` and maps the incorrect string via `migrations`, so ndr keeps working.
- Realtime/audio and video models (`gpt-realtime-*`, `sora-*`, Gemini Live) and the
  pre-`gpt-4o` OpenAI lineup in `seed_pricing.py` are deliberately out of scope: no
  consumer of this registry references them.
