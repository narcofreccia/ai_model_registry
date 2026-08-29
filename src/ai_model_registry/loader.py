"""Loading a Registry, with fallbacks that keep consumers running offline."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Any

from .accessors import Registry

logger = logging.getLogger(__name__)

STABLE_URL = (
    "https://raw.githubusercontent.com/narcofreccia/ai_model_registry/"
    "stable/registry.json"
)

CACHE_FILENAME = "registry.json"
FETCH_TIMEOUT_SECONDS = 5.0


def load(
    snapshot_path: str | os.PathLike[str] | None = None,
    cache_dir: str | os.PathLike[str] | None = None,
    fetch: bool = False,
    url: str = STABLE_URL,
) -> Registry:
    """Load the registry, trying sources in order of freshness.

    Precedence: ``fetch`` (network, 5s timeout — also refreshes ``cache_dir``)
    -> last good copy in ``cache_dir`` -> ``snapshot_path`` -> the copy packaged
    with this library.

    Never raises for a failed fetch or an unreadable file while another source
    remains; only a total failure of every source raises RuntimeError.
    """
    errors: list[str] = []

    if fetch:
        payload = _fetch(url, errors)
        if payload is not None:
            if cache_dir is not None:
                _write_cache(Path(cache_dir), payload, errors)
            registry = _parse(payload, f"fetch {url}", errors)
            if registry is not None:
                return registry

    if cache_dir is not None:
        registry = _load_file(Path(cache_dir) / CACHE_FILENAME, errors)
        if registry is not None:
            return registry

    if snapshot_path is not None:
        registry = _load_file(Path(snapshot_path), errors)
        if registry is not None:
            return registry

    registry = _load_packaged(errors)
    if registry is not None:
        return registry

    raise RuntimeError(
        "ai_model_registry: no usable registry source. Tried:\n  "
        + "\n  ".join(errors)
    )


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def _fetch(url: str, errors: list[str]) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return response.read()
    except Exception as exc:  # network, DNS, HTTP, timeout — all non-fatal
        message = f"fetch {url}: {exc}"
        logger.warning("ai_model_registry: %s (falling back)", message)
        errors.append(message)
        return None


def _write_cache(cache_dir: Path, payload: bytes, errors: list[str]) -> None:
    """Persist a fetched registry as the last-good copy (atomic replace)."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=cache_dir, delete=False, suffix=".tmp"
        ) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        temp_path.replace(cache_dir / CACHE_FILENAME)
    except Exception as exc:  # a read-only cache dir must not break loading
        message = f"cache write {cache_dir}: {exc}"
        logger.warning("ai_model_registry: %s", message)
        errors.append(message)


def _load_file(path: Path, errors: list[str]) -> Registry | None:
    try:
        payload = path.read_bytes()
    except Exception as exc:
        errors.append(f"read {path}: {exc}")
        return None
    return _parse(payload, str(path), errors)


def _load_packaged(errors: list[str]) -> Registry | None:
    try:
        payload = (
            resources.files("ai_model_registry")
            .joinpath("registry.json")
            .read_bytes()
        )
    except Exception as exc:
        errors.append(f"packaged registry.json: {exc}")
        # Source checkout (not installed): registry.json sits at the repo root.
        return _load_file(Path(__file__).resolve().parents[2] / "registry.json", errors)
    return _parse(payload, "packaged registry.json", errors)


def _parse(payload: bytes, source: str, errors: list[str]) -> Registry | None:
    try:
        data: Any = json.loads(payload)
        return Registry.model_validate(data)
    except Exception as exc:
        message = f"parse {source}: {exc}"
        logger.warning("ai_model_registry: %s (falling back)", message)
        errors.append(message)
        return None
