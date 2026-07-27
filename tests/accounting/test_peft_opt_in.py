from __future__ import annotations

import builtins

import pytest

from butler_pc_core.accounting import ft_classifier


def _reset_peft_state() -> None:
    ft_classifier._peft_model = None
    ft_classifier._peft_tokenizer = None
    ft_classifier._peft_loaded = False
    ft_classifier._peft_attempted = False
    ft_classifier._peft_backend = None


@pytest.fixture(autouse=True)
def reset_peft_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ACCOUNTING_NO_PEFT", raising=False)
    monkeypatch.delenv("ACCOUNTING_ENABLE_PEFT", raising=False)
    _reset_peft_state()
    yield
    _reset_peft_state()


def _block_heavy_imports(monkeypatch: pytest.MonkeyPatch, seen: list[str]) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        root_name = name.split(".", 1)[0]
        if root_name in {"torch", "transformers", "peft"}:
            seen.append(root_name)
            raise AssertionError(f"PEFT heavy import attempted without opt-in: {root_name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_peft_default_has_no_path_discovery_or_heavy_imports(monkeypatch: pytest.MonkeyPatch):
    heavy_imports: list[str] = []
    _block_heavy_imports(monkeypatch, heavy_imports)

    assert ft_classifier.load_peft() is False
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False
    assert heavy_imports == []


def test_environment_poison_cannot_enable_peft(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCOUNTING_ENABLE_PEFT", "1")
    monkeypatch.setenv("ACCOUNTING_PEFT_ADAPTER_PATH", "/tmp/untrusted-adapter")

    assert ft_classifier.load_peft() is False
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False


def test_explicit_verified_backend_is_the_only_load_authority():
    class Backend:
        calls = 0

        def load(self):
            self.calls += 1
            return object(), object()

    backend = Backend()
    ft_classifier._peft_backend = backend

    assert ft_classifier.load_peft() is True
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is True
    assert backend.calls == 1


def test_default_rule_based_food_expense(monkeypatch: pytest.MonkeyPatch):
    heavy_imports: list[str] = []
    _block_heavy_imports(monkeypatch, heavy_imports)

    result = ft_classifier.ft_classify("식대", "", 12_000, direction="출금")

    assert result.category == "복리후생비"
    assert result.source == "rule_base"
    assert result.confidence > 0
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False
    assert heavy_imports == []
