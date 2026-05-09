"""test_finetuned_accuracy.py — Phase 7 어댑터 통합 + 회계 카드 재테스트.

Tests:
  1. adapter_files_present           — 어댑터 파일 9개 존재 확인
  2. adapter_config_base_model       — base_model_name_or_path == Qwen/Qwen3-4B
  3. peft_find_adapter_path          — _find_adapter() returns valid path
  4. d2_jibeoum_expense_section_sign — D-2 Case1: 자문료 출금 → IV_sga / (-)
  5. d2_jibeoum_income_override      — D-2 Case2: 자문 수입 입금 → I_revenue / (+)
  6. d2_imdaeryo_expense             — D-2 Case3: 임대료 지급 → IV_sga / (-)
  7. d2_imdae_income                 — D-2 Case4: 임대 수입 입금 → I_revenue / (+)
  8. d2_resolution_rate_above_80pct  — D-2 4건 모두 통과 ≥80%
  9. labeled_section_accuracy_sample — 200개 샘플 section 정확도 ≥75%
 10. labeled_sign_accuracy_sample    — 200개 샘플 sign 정확도 ≥85%
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

_ADAPTER_DIR = (
    Path(__file__).parent.parent.parent
    / "butler_pc_core" / "accounting" / "models" / "qwen3_4b_accounting_v1"
)
_LABELED = Path(__file__).parent / "test_labeled.jsonl"

_REQUIRED_ADAPTER_FILES = [
    "adapter_config.json",
    "adapter_model.safetensors",
    "added_tokens.json",
    "merges.txt",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "training_args.bin",
    "vocab.json",
]


# ── 1. 어댑터 파일 존재 확인 ──────────────────────────────────────────────────
def test_adapter_files_present():
    """어댑터 디렉터리에 필수 파일 9개가 존재해야 한다."""
    missing = [f for f in _REQUIRED_ADAPTER_FILES if not (_ADAPTER_DIR / f).exists()]
    assert not missing, f"어댑터 파일 누락: {missing}"


# ── 2. adapter_config 기본 모델 확인 ─────────────────────────────────────────
def test_adapter_config_base_model():
    """adapter_config.json 의 base_model_name_or_path 가 Qwen/Qwen3-4B 여야 한다."""
    cfg = json.loads((_ADAPTER_DIR / "adapter_config.json").read_text())
    assert cfg["base_model_name_or_path"] == "Qwen/Qwen3-4B"


# ── 3. _find_adapter() 경로 반환 확인 ────────────────────────────────────────
def test_peft_find_adapter_path():
    """_find_adapter()가 어댑터 경로를 찾아야 한다."""
    from butler_pc_core.accounting.ft_classifier import _find_adapter

    path = _find_adapter()
    assert path is not None, "_find_adapter()가 None 반환 — 어댑터 미발견"
    assert (path / "adapter_model.safetensors").exists()


# ── D-2 C/D 결함 4건 ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def classifier():
    from butler_pc_core.accounting.ft_classifier import ft_classify
    return ft_classify


def test_d2_jibeoum_expense_section_sign(classifier):
    """D-2 Case1: 자문료 출금 → 지급수수료 / IV_sga / (-)."""
    r = classifier("ABC컨설팅 자문료 5,000,000원 송금", "", 5_000_000, "출금")
    assert r.category == "지급수수료", f"category={r.category}"
    assert r.section == "IV_sga", f"section={r.section}"
    assert r.sign == "-", f"sign={r.sign}"


def test_d2_jibeoum_income_override(classifier):
    """D-2 Case2: 자문 수입 입금 → 용역매출 / I_revenue / (+)."""
    r = classifier("ABC컨설팅 자문 수입 5,000,000원 입금", "", 5_000_000, "입금")
    assert r.category == "용역매출", f"category={r.category}"
    assert r.section == "I_revenue", f"section={r.section}"
    assert r.sign == "+", f"sign={r.sign}"


def test_d2_imdaeryo_expense(classifier):
    """D-2 Case3: 임대료 지급 → 지급임차료 / IV_sga / (-)."""
    r = classifier("한국빌딩 임대료 3,000,000원 지급", "", 3_000_000, "출금")
    assert r.category == "지급임차료", f"category={r.category}"
    assert r.section == "IV_sga", f"section={r.section}"
    assert r.sign == "-", f"sign={r.sign}"


def test_d2_imdae_income(classifier):
    """D-2 Case4: 임대 수입 입금 → 임대수입 / I_revenue / (+)."""
    r = classifier("한국빌딩 임대 수입 5,000,000원 입금", "", 5_000_000, "입금")
    assert r.category == "임대수입", f"category={r.category}"
    assert r.section == "I_revenue", f"section={r.section}"
    assert r.sign == "+", f"sign={r.sign}"


# ── 8. D-2 4건 해소율 ≥80% ────────────────────────────────────────────────────
def test_d2_resolution_rate_above_80pct(classifier):
    """D-2 C/D 결함 4건 모두 정확히 분류돼야 한다 (해소율 ≥80%)."""
    cases = [
        ("ABC컨설팅 자문료 5,000,000원 송금", "", 5_000_000, "출금",
         "지급수수료", "IV_sga", "-"),
        ("ABC컨설팅 자문 수입 5,000,000원 입금", "", 5_000_000, "입금",
         "용역매출", "I_revenue", "+"),
        ("한국빌딩 임대료 3,000,000원 지급", "", 3_000_000, "출금",
         "지급임차료", "IV_sga", "-"),
        ("한국빌딩 임대 수입 5,000,000원 입금", "", 5_000_000, "입금",
         "임대수입", "I_revenue", "+"),
    ]
    passed = sum(
        1 for (desc, vendor, amt, direction, exp_cat, exp_sec, exp_sign) in cases
        if (r := classifier(desc, vendor, amt, direction))
        and r.category == exp_cat and r.section == exp_sec and r.sign == exp_sign
    )
    rate = passed / len(cases)
    assert rate >= 0.80, f"D-2 해소율 {rate:.0%} < 80% ({passed}/{len(cases)})"


# ── 9–10. test_labeled.jsonl 샘플 정확도 ─────────────────────────────────────
@pytest.fixture(scope="module")
def labeled_sample():
    if not _LABELED.exists():
        pytest.skip("test_labeled.jsonl 없음")
    records = [json.loads(l) for l in _LABELED.read_text().splitlines() if l.strip()]
    rng = random.Random(42)
    return rng.sample(records, min(200, len(records)))


def test_labeled_section_accuracy_sample(classifier, labeled_sample):
    """200개 샘플에서 section 정확도 ≥75%."""
    ok = sum(
        1 for r in labeled_sample
        if classifier(r["input"], "", 0.0, None).section == r["label"]["section"]
    )
    acc = ok / len(labeled_sample)
    assert acc >= 0.75, f"section 정확도 {acc:.1%} < 75% ({ok}/{len(labeled_sample)})"


def test_labeled_sign_accuracy_sample(classifier, labeled_sample):
    """200개 샘플에서 sign 정확도 ≥85%."""
    ok = sum(
        1 for r in labeled_sample
        if classifier(r["input"], "", 0.0, None).sign == r["label"]["sign"]
    )
    acc = ok / len(labeled_sample)
    assert acc >= 0.85, f"sign 정확도 {acc:.1%} < 85% ({ok}/{len(labeled_sample)})"
