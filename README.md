# ai_model_registry

One place for AI model **facts**: ids, providers, capabilities, current USD list prices,
lifecycle status, and id migrations. No behavior — request settings, routing, prompts and
per-app overlays stay in the consuming app.

Maintainer checklists (adding a model, changing a price, deprecating, promoting `stable`)
live in [MAINTAINING.md](MAINTAINING.md).

## What's in it

| | |
|---|---|
| `registry.json` | the single artifact consumers read (the whole contract) |
| `schema/registry.schema.json` | JSON Schema draft 2020-12 |
| `scripts/validate.py` | schema + invariant checks (CI gate) |
| `src/ai_model_registry/` | optional Python adapter (`pip install`-able) |

## Consuming

### Option A — raw URL (any language)

```
https://raw.githubusercontent.com/narcofreccia/ai_model_registry/stable/registry.json
```

`stable` is a force-moved tag, advanced only by the CI *promote* job after validation.
Anything on `main` may be mid-edit; always read `stable`.

### Option B — Python adapter

```bash
# Heroku requirements.txt (re-resolved on every deploy)
ai-model-registry @ git+https://github.com/narcofreccia/ai_model_registry.git@stable

# reproducible builds (PyInstaller/desktop): pin the SHA instead of the tag
ai-model-registry @ git+https://github.com/narcofreccia/ai_model_registry.git@<40-char-sha>
```

```python
from ai_model_registry import load

registry = load(cache_dir="/tmp/model_registry", fetch=True)   # offline-safe
model = registry.resolve("gpt-4o")                # migrated -> gpt-5.6-terra
print(model.api_model_id, model.responses_api)    # what to send, how to send it
price = registry.get_price("claude-opus-5")       # -> $5 / $25 per 1M
chat = [m for m in registry.models_by_kind("chat") if m.status == "active"]
```

### `load()` precedence

`load(snapshot_path=None, cache_dir=None, fetch=False, url=STABLE_URL)` tries, in order:

1. **fetch** — the raw `stable` URL, 5s timeout (only when `fetch=True`); a success also
   rewrites `cache_dir/registry.json` as the new last-good copy
2. **cache** — `cache_dir/registry.json`
3. **snapshot** — the `snapshot_path` file you vendored in your app
4. **packaged** — the `registry.json` shipped inside this library

A failed fetch, an unreachable network or a corrupt file is logged and skipped, never
raised, as long as a fallback remains. Only a total failure of all four raises.

### Registry API

| call | returns |
|---|---|
| `.providers` / `.models` / `.migrations` | raw data |
| `.get(id)` | model by id → alias → `api_model_id` (no migration applied) |
| `.resolve_migration(id)` | current id (chained, cycle-safe) |
| `.resolve(id)` | migrate, then look up |
| `.models_by_kind(kind=None)` / `.models_by_provider(p=None)` | list, or dict of all |
| `.get_price(id)` | current base `Pricing`, or `None` when unpriced |

### Model kinds and their pricing shapes

| `kind` | pricing fields |
|---|---|
| `chat`, `embedding` | `input_per_1m`, `output_per_1m`, `cached_input_per_1m` |
| `image_gen` | `per_image` |
| `realtime` | `audio_input_per_1m`, `audio_output_per_1m`, `text_input_per_1m`, `text_output_per_1m`, `cached_input_per_1m` (+ optional `cached_audio_input_per_1m`) |

`Pricing` is one Python class with every field optional, so reading the wrong shape yields
`None`, never an exception; `Pricing.is_realtime` tells the realtime shape apart. Realtime
models also carry `voices` (the voice ids the provider accepts) and `modalities` (the
session modality tokens, spelled as the API wants them: OpenAI `["text","audio"]`, Google
Live `["AUDIO"]`).

### Rules consumers must follow

- **Ignore model kinds you don't handle.** New kinds are added additively (`realtime`
  arrived in schema 1.1); filter by the kinds you know instead of rejecting the rest.
- **`get_price(id)` migrates first.** For a deprecated-but-still-callable id, that returns
  the *successor's* rates. A biller charging that id verbatim must read
  `registry.get(id).pricing` instead.
- **Ignore unknown `pricing.variants[].condition` values.** The vocabulary is open
  (`off_peak`, `batch`, `long_context_gt_200k`, …); a new condition must never break you.
  Fall back to the base rate when you don't recognise one.
- **Ignore unknown `reasoning` values** — the adapter already degrades them to `"none"`
  with a warning.
- `pricing: null` means *no verified price*, not free.
- The registry carries only the **current** price. Historical rates are in git history.
- Model list order is part of the contract; the active chat models are in tide_share's
  catalog order.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/validate.py
.venv/bin/python -m pytest
```
