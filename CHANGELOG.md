# Changelog

Dates are the promotion date (when `stable` was moved), not the merge date.

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
