import json
from pathlib import Path

import pytest

from butler.card5 import inference


def test_inference_requires_runner():
    with pytest.raises(RuntimeError, match="mlx_runner is required"):
        inference.run_inference("테스트 거래", mlx_runner=None)


def test_inference_hallucination_sets_needs_review(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")

    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(
        inference,
        "build_system_prompt",
        lambda transaction: f"prompt: {transaction}",
    )

    def runner(prompt: str, adapter_path: Path) -> str:
        return json.dumps(
            {
                "account_title": "매출 수익",
                "account_code": "50",
                "needs_review": False,
                "confidence": 0.99,
            },
            ensure_ascii=False,
        )

    out = inference.run_inference("거래", mlx_runner=runner)

    assert out.match_kind == "hallucination"
    assert out.needs_review is True
    assert out.rollback_triggered is True


def test_inference_exact_allowlist(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")

    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(inference, "build_system_prompt", lambda transaction: "prompt")

    def runner(prompt: str, adapter_path: Path) -> str:
        return json.dumps(
            {
                "account_title": "통신비",
                "account_code": "8080",
                "needs_review": False,
                "confidence": 0.91,
            },
            ensure_ascii=False,
        )

    out = inference.run_inference("거래", mlx_runner=runner)

    assert out.account_title == "통신비"
    assert out.account_code == "8080"
    assert out.match_kind == "exact"
    assert out.rollback_triggered is False


def test_inference_rejects_non_dict_json(monkeypatch, tmp_path: Path):
    """P1 #1: JSON 출력이 객체 아닌 경우 (배열/문자열) BLOCK."""
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"adapter")

    monkeypatch.setattr(inference, "verify_and_locate_adapter", lambda: adapter)
    monkeypatch.setattr(inference, "verify_invariants", lambda _: None)
    monkeypatch.setattr(inference, "build_system_prompt", lambda transaction: "prompt")

    # JSON array (not object)
    def array_runner(prompt: str, adapter_path: Path) -> str:
        return "[]"

    with pytest.raises(RuntimeError, match="JSON output must be an object"):
        inference.run_inference("거래", mlx_runner=array_runner)

    # JSON string (not object)
    def string_runner(prompt: str, adapter_path: Path) -> str:
        return '"ok"'

    with pytest.raises(RuntimeError, match="JSON output must be an object"):
        inference.run_inference("거래", mlx_runner=string_runner)
