"""Lookups over a loaded registry."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .types import Kind, Model, Pricing, PricingVariant, RegistryData


class Registry(RegistryData):
    """Registry data plus the accessors consumers actually call."""

    # -- indexes ----------------------------------------------------------
    def models_by_kind(self, kind: Kind | str | None = None):
        """All models grouped by kind, or just the list for one ``kind``."""
        grouped: dict[str, list[Model]] = {}
        for model in self.models:
            grouped.setdefault(model.kind, []).append(model)
        if kind is None:
            return grouped
        return grouped.get(kind, [])

    def models_by_provider(self, provider: str | None = None):
        """All models grouped by provider key, or just one provider's list."""
        grouped: dict[str, list[Model]] = {}
        for model in self.models:
            grouped.setdefault(model.provider, []).append(model)
        if provider is None:
            return grouped
        return grouped.get(provider, [])

    # -- lookup -----------------------------------------------------------
    def get(self, model_id: str) -> Model | None:
        """Find a model by id, alias, or api_model_id (in that order).

        Migrations are NOT applied here — call :meth:`resolve_migration` first
        when the id may be stale.
        """
        for model in self.models:
            if model.id == model_id:
                return model
        for model in self.models:
            if model_id in model.aliases:
                return model
        for model in self.models:
            if model.api_model_id == model_id:
                return model
        return None

    def resolve(self, model_id: str) -> Model | None:
        """Migrate a possibly-stale id, then look it up."""
        return self.get(self.resolve_migration(model_id))

    def resolve_migration(self, model_id: str) -> str:
        """Apply migrations to a possibly-stale id (chained, cycle-safe)."""
        seen: set[str] = set()
        current = model_id
        while current in self.migrations and current not in seen:
            seen.add(current)
            current = self.migrations[current]
        return current

    # -- pricing ----------------------------------------------------------
    def get_price(self, model_id: str) -> Pricing | None:
        """The model's CURRENT base USD list price, or None when unknown.

        The shape follows the model's kind: token models fill
        ``input_per_1m``/``output_per_1m``, image models ``per_image``, and
        realtime models the audio/text axes (``audio_input_per_1m``,
        ``audio_output_per_1m``, ``text_input_per_1m``, ``text_output_per_1m``
        — ``Pricing.is_realtime`` tells them apart). Unread fields are None, so
        a caller that only knows one shape is unaffected by the others.

        Conditional rates (off-peak, batch, ...) hang off ``Pricing.variants``;
        this returns the base price unchanged.
        """
        model = self.resolve(model_id)
        return model.pricing if model else None

    def price_for(
        self,
        model_id: str,
        *,
        input_tokens: int | None = None,
        conditions: Iterable[str] = (),
    ) -> Pricing | None:
        """The rate that applies to ONE request, or None when unknown.

        Starts from the base price and overlays the variants that apply:

        * ``long_context_gt_<N>k`` when ``input_tokens`` (that request's input,
          never a whole run's total) exceeds N*1000 — only the highest such
          threshold applies, as providers bill the whole request at that card;
        * every variant named in ``conditions`` (e.g. ``image_size_4k``), in
          order.

        A rate the variant leaves unset keeps the base value. Conditions the
        model does not publish are ignored. The result carries no variants.
        """
        base = self.get_price(model_id)
        if base is None:
            return None
        applied: list[PricingVariant] = []
        if input_tokens is not None:
            tiers = [
                (int(m.group(1)) * 1000, v)
                for v in base.variants
                if (m := _LONG_CONTEXT.fullmatch(v.condition))
            ]
            over = [t for t in tiers if input_tokens > t[0]]
            if over:
                applied.append(max(over, key=lambda t: t[0])[1])
        for condition in conditions:
            variant = base.variant(condition)
            if variant is not None:
                applied.append(variant)
        update: dict[str, float] = {}
        for variant in applied:
            for key in _VARIANT_RATE_KEYS:
                value = getattr(variant, key)
                if value is not None:
                    update[key] = value
        return base.model_copy(update={**update, "variants": ()})


_LONG_CONTEXT = re.compile(r"long_context_gt_(\d+)k")
_VARIANT_RATE_KEYS = ("input_per_1m", "output_per_1m", "cached_input_per_1m", "per_image")
