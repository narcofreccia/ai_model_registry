"""Centralized AI model registry — facts only (ids, capabilities, USD prices).

    from ai_model_registry import load
    registry = load()
    model = registry.resolve("gpt-4o")          # migrated -> gpt-5.6-terra
"""

from .accessors import Registry
from .loader import STABLE_URL, load
from .types import Model, Pricing, PricingVariant, Provider, RegistryData

__all__ = [
    "load",
    "Registry",
    "RegistryData",
    "Model",
    "Provider",
    "Pricing",
    "PricingVariant",
    "STABLE_URL",
]

__version__ = "0.1.0"
