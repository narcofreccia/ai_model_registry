"""Frozen pydantic models mirroring registry.json.

Facts only — no request settings, no routing, no prompts. Consumers keep their
own behavior layer and read these as data.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

Kind = Literal["chat", "realtime", "embedding", "image_gen"]
Status = Literal["active", "deprecated", "retired"]
Reasoning = Literal[
    "adaptive",
    "anthropic_budget",
    "openai_effort",
    "google_budget",
    "openrouter_reasoning",
    "glm_thinking",
    "none",
]

_KNOWN_REASONING = frozenset(
    ["adaptive", "anthropic_budget", "openai_effort", "google_budget",
     "openrouter_reasoning", "glm_thinking", "none"]
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Provider(_Frozen):
    """Provider facts: where it lives and which env var holds its key."""

    name: str
    base_url: str | None = None
    key_env: str | None = None
    pydantic_ai_prefix: str | None = None


class PricingVariant(_Frozen):
    """A conditional rate (off-peak, batch, long-context, quality tier...).

    ``condition`` is an OPEN vocabulary. Consumers MUST ignore conditions they
    do not recognise and fall back to the base price — a new condition is never
    a breaking change.
    """

    condition: str
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    cached_input_per_1m: float | None = None
    per_image: float | None = None
    note: str | None = None


class Pricing(_Frozen):
    """CURRENT USD list price. Historical rates live in git history, not here.

    Token models populate ``input_per_1m``/``output_per_1m``; image models
    populate ``per_image``. ``variants`` is optional and defaults to empty, so
    a consumer reading only the base fields is never affected by it.
    """

    input_per_1m: float | None = None
    output_per_1m: float | None = None
    cached_input_per_1m: float | None = None
    per_image: float | None = None
    effective_from: str | None = None
    variants: tuple[PricingVariant, ...] = ()

    def variant(self, condition: str) -> PricingVariant | None:
        """The variant for ``condition``, or None when it is not published."""
        for v in self.variants:
            if v.condition == condition:
                return v
        return None


class Model(_Frozen):
    """One catalog entry."""

    id: str
    name: str
    description: str = ""
    provider: str
    kind: Kind = "chat"
    api_model_id: str
    aliases: tuple[str, ...] = ()
    reasoning: Reasoning = "none"
    allows_temperature: bool = True
    responses_api: bool = False
    server_web_tools: bool = False
    vision: bool = False
    needs_pdf_rasterization: bool = False
    max_reference_images: int | None = None
    voices: tuple[str, ...] | None = None
    status: Status = "active"
    pricing: Pricing | None = None

    @field_validator("reasoning", mode="before")
    @classmethod
    def _degrade_unknown_reasoning(cls, value: Any) -> Any:
        """A registry newer than this adapter may carry a reasoning mode we do
        not know. Degrade it to "none" with a warning instead of failing to
        load the whole registry."""
        if isinstance(value, str) and value not in _KNOWN_REASONING:
            logger.warning(
                "Unknown reasoning mode %r in registry — treating as 'none'. "
                "Upgrade ai-model-registry to use it.",
                value,
            )
            return "none"
        return value

    @property
    def supports_reasoning(self) -> bool:
        return self.reasoning != "none"


class RegistryData(_Frozen):
    """The whole registry document. ``accessors.Registry`` adds the lookups."""

    schema_version: int
    generated_at: str
    providers: dict[str, Provider] = Field(default_factory=dict)
    models: tuple[Model, ...] = ()
    migrations: dict[str, str] = Field(default_factory=dict)
