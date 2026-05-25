from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.card5 import inference
from butler.card5.alias_map import apply_alias


def test_alias_and_rollback_exact_allowlist_title_pattern():
    title, code, kind = apply_alias("통신비", "0000")
    assert title == "통신비"
    assert code == "8080"
    assert kind == "exact"


def test_alias_and_rollback_alias_maps_to_allowlist_code_pattern():
    title, code, kind = apply_alias("서비스매출", "9999")
    assert title == "용역매출"
    assert code == "4040"
    assert kind == "alias_mapped"


def test_inference_hallucination_sets_needs_review_pattern(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(inference, "build_system_prompt", lambda transaction: "prompt")

    def runner(prompt: str, adapter_path: Path) -> str:
        return json.dumps(
            {"account_title": "매출 수익", "account_code": "50", "needs_review": False, "confidence": 0.99},
            ensure_ascii=False,
        )

    out = inference.run_inference("거래", mlx_runner=runner)
    assert out.match_kind == "hallucination"
    assert out.needs_review is True
    assert out.rollback_triggered is True


def test_inference_exact_allowlist_pattern(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(inference, "build_system_prompt", lambda transaction: "prompt")

    def runner(prompt: str, adapter_path: Path) -> str:
        return json.dumps(
            {"account_title": "통신비", "account_code": "8080", "needs_review": False, "confidence": 0.91},
            ensure_ascii=False,
        )

    out = inference.run_inference("거래", mlx_runner=runner)
    assert out.account_title == "통신비"
    assert out.account_code == "8080"
    assert out.match_kind == "exact"
    assert out.rollback_triggered is False


def test_inference_rejects_non_dict_json_pattern(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")
    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(inference, "build_system_prompt", lambda transaction: "prompt")

    def array_runner(prompt: str, adapter_path: Path) -> str:
        return "[]"

    with pytest.raises(RuntimeError, match="JSON output must be an object"):
        inference.run_inference("거래", mlx_runner=array_runner)

    def string_runner(prompt: str, adapter_path: Path) -> str:
        return '"ok"'

    with pytest.raises(RuntimeError, match="JSON output must be an object"):
        inference.run_inference("거래", mlx_runner=string_runner)

