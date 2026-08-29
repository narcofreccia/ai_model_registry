# Changelog

Dates are the promotion date (when `stable` was moved), not the merge date.

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
