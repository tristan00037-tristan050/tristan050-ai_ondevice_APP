from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from butler_pc_core.accounting import ft_classifier


def _reset_peft_state() -> None:
    if ft_classifier._peft_materialized is not None:
        ft_classifier._peft_materialized.close()
    ft_classifier._peft_model = None
    ft_classifier._peft_tokenizer = None
    ft_classifier._peft_loaded = False
    ft_classifier._peft_attempted = False
    ft_classifier._peft_materialized = None
    ft_classifier._peft_base_path = None


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


def test_peft_default_disabled_even_if_adapter_exists(monkeypatch: pytest.MonkeyPatch):
    find_calls = {"count": 0}
    heavy_imports: list[str] = []

    def fake_find_adapter() -> Path:
        find_calls["count"] += 1
        return Path("/tmp/fake-accounting-adapter")

    monkeypatch.setattr(ft_classifier, "_find_adapter", fake_find_adapter)
    _block_heavy_imports(monkeypatch, heavy_imports)

    assert ft_classifier.load_peft() is False
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False
    assert find_calls["count"] == 0
    assert heavy_imports == []


def test_no_peft_overrides_enable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCOUNTING_NO_PEFT", "1")
    monkeypatch.setenv("ACCOUNTING_ENABLE_PEFT", "1")
    monkeypatch.setattr(
        ft_classifier,
        "_find_adapter",
        lambda: pytest.fail("ACCOUNTING_NO_PEFT must prevent adapter discovery"),
    )

    assert ft_classifier.load_peft() is False
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False


def test_enable_peft_attempts_adapter_load(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCOUNTING_ENABLE_PEFT", "1")
    find_calls = {"count": 0}
    import_attempts: list[str] = []
    original_import = builtins.__import__

    def fake_find_adapter() -> Path:
        find_calls["count"] += 1
        ft_classifier._peft_base_path = Path("/tmp/fake-accounting-base")
        return Path("/tmp/fake-accounting-adapter")

    def import_probe(name, *args, **kwargs):
        root_name = name.split(".", 1)[0]
        if root_name == "torch":
            import_attempts.append(root_name)
            raise ImportError("test blocks actual Qwen/PEFT runtime load")
        if root_name in {"transformers", "peft"}:
            import_attempts.append(root_name)
            raise AssertionError(f"runtime load advanced past torch probe: {root_name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(ft_classifier, "_find_adapter", fake_find_adapter)
    monkeypatch.setattr(builtins, "__import__", import_probe)

    assert ft_classifier.load_peft() is False
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False
    assert find_calls["count"] == 1
    assert import_attempts == ["torch"]


def test_default_rule_based_food_expense(monkeypatch: pytest.MonkeyPatch):
    find_calls = {"count": 0}
    heavy_imports: list[str] = []

    def fake_find_adapter() -> Path:
        find_calls["count"] += 1
        return Path("/tmp/fake-accounting-adapter")

    monkeypatch.setattr(ft_classifier, "_find_adapter", fake_find_adapter)
    _block_heavy_imports(monkeypatch, heavy_imports)

    result = ft_classifier.ft_classify("식대", "", 12_000, direction="출금")

    assert result.category == "복리후생비"
    assert result.source == "rule_base"
    assert result.confidence > 0
    assert ft_classifier._peft_attempted is True
    assert ft_classifier._peft_loaded is False
    assert find_calls["count"] == 0
    assert heavy_imports == []
