"""Lookups over a loaded registry."""

from __future__ import annotations

from .types import Kind, Model, Pricing, RegistryData


class Registry(RegistryData):
    """Registry data plus the accessors consumers actually call."""

    # -- indexes ----------------------------------------------------------
    def models_by_kind(self, kind: Kind | None = None):
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

        Conditional rates (off-peak, batch, ...) hang off ``Pricing.variants``;
        this returns the base price unchanged.
        """
        model = self.resolve(model_id)
        return model.pricing if model else None
