import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def registry_dict() -> dict:
    return json.loads((REPO / "registry.json").read_text())


@pytest.fixture
def make_registry_file(tmp_path, registry_dict):
    """Write a (optionally mutated) registry to a file and return the path."""

    def _make(name: str, **overrides) -> Path:
        data = json.loads(json.dumps(registry_dict))
        data.update(overrides)
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    return _make
