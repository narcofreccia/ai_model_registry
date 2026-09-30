"""scripts/consumers.py: pin parsing/rewriting and the adapter-compatibility check."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OLD = "9a1d73882497fae9bbfeaefe8cd4357465a669a8"
NEW = "219948ca7de72d4825807c39e0f0077d1af00743"


@pytest.fixture(scope="module")
def consumers():
    spec = importlib.util.spec_from_file_location("registry_consumers", REPO / "scripts" / "consumers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks the module up while decorating
    spec.loader.exec_module(module)
    return module


def test_rewrites_requirements_line(consumers):
    text = (
        "# ai-model-registry is SHA-pinned\n"
        f"ai-model-registry @ git+https://github.com/narcofreccia/ai_model_registry.git@{OLD}\n"
        "pydantic>=2\n"
    )
    new_text, count = consumers.rewrite_pins(text, NEW)
    assert count == 1
    assert consumers.read_pins(new_text) == [NEW]
    assert new_text.replace(NEW, OLD) == text


def test_rewrites_pyproject_string_and_keeps_quotes(consumers):
    text = f'dependencies = [\n  "ai-model-registry @ git+https://github.com/narcofreccia/ai_model_registry.git@{OLD}",\n]\n'
    new_text, count = consumers.rewrite_pins(text, NEW)
    assert count == 1
    assert f'.git@{NEW}",' in new_text


def test_tag_pins_are_rewritten_too(consumers):
    text = "ai-model-registry @ git+https://github.com/narcofreccia/ai_model_registry.git@stable\n"
    assert consumers.read_pins(text) == ["stable"]
    assert consumers.rewrite_pins(text, NEW)[0].endswith(f"@{NEW}\n")


def test_other_git_deps_are_left_alone(consumers):
    text = f"other @ git+https://github.com/narcofreccia/other_repo.git@{OLD}\n"
    assert consumers.rewrite_pins(text, NEW) == (text, 0)


def test_adapter_accepts_checks_kind_literal(consumers, monkeypatch):
    closed = 'Kind = Literal["chat", "realtime", "embedding", "image_gen"]\n    kind: Kind = "chat"\n'
    tolerant = 'Kind = Literal["chat", "decision"]\n    kind: Kind | str = "chat"\n'
    files = {"old": closed, "new": tolerant}
    monkeypatch.setattr(consumers, "show", lambda sha, path: files.get(sha))
    with_decision = {"models": [{"kind": "chat"}, {"kind": "decision"}]}
    chat_only = {"models": [{"kind": "chat"}]}

    assert consumers.adapter_accepts("old", chat_only)[0]
    ok, why = consumers.adapter_accepts("old", with_decision)
    assert not ok and "decision" in why
    assert consumers.adapter_accepts("new", {"models": [{"kind": "someday"}]})[0]
    assert not consumers.adapter_accepts("missing", chat_only)[0]
