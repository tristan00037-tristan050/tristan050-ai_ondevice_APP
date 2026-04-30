"""test_card05_accuracy_gate.py — card_05 분류 정확도 게이트 (5 cases)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys_path_inserted = False

try:
    from scripts.eval.card05_accuracy import run, classify, load_codes, GATE_OVERALL, GATE_PER_CATEGORY
except ImportError:
    import sys
    sys.path.insert(0, str(_REPO))
    from scripts.eval.card05_accuracy import run, classify, load_codes, GATE_OVERALL, GATE_PER_CATEGORY

_SAMPLES = _REPO / "tests/fixtures/card05_bank_samples/synthetic_100.jsonl"
_CODES = _REPO / "butler_pc_core/data/accounting_codes/default_v2.json"


@pytest.fixture(scope="module")
def eval_result(tmp_path_factory):
    out = tmp_path_factory.mktemp("card05_eval")
    return run(samples_path=_SAMPLES, codes_path=_CODES, out_dir=out)


def test_happy_overall_90pct_pass(eval_result):
    """overall_accuracy >= 0.90 게이트 통과."""
    acc = eval_result["overall_accuracy"]
    assert acc >= GATE_OVERALL, (
        f"overall_accuracy {acc:.1%} < {GATE_OVERALL:.0%} 기준 미달"
    )


def test_boundary_per_category_80pct(eval_result):
    """모든 카테고리 accuracy >= 0.80."""
    failing = {
        cat: acc
        for cat, acc in eval_result["per_category_accuracy"].items()
        if acc < GATE_PER_CATEGORY
    }
    assert not failing, (
        f"카테고리별 80% 미달: {failing}"
    )


def test_adv_no_critical_misclassification(eval_result):
    """절대 금지 오분류 0건."""
    assert eval_result["critical_violations"] == 0, (
        f"절대 금지 오분류 {eval_result['critical_violations']}건 발생"
    )


def test_adv_account_code_map_override(tmp_path):
    """account_code_map 커스텀 오버라이드 시 해당 매핑이 우선 적용된다."""
    codes = load_codes(_CODES)
    # "소프트웨어" 키워드를 커스텀 코드로 오버라이드
    custom_codes = dict(codes)
    custom_codes["소프트웨어라이선스"] = {
        "code": "9500", "name": "소프트웨어라이선스", "category": "asset",
        "keywords": ["소프트웨어", "라이선스"],
    }
    predicted = classify("소프트웨어 라이선스 구입", -500000, custom_codes)
    assert predicted == "소프트웨어라이선스", (
        f"커스텀 코드가 오버라이드되지 않음: {predicted}"
    )


def test_adv_empty_description_safe_handling():
    """빈 설명/비정상 입력도 예외 없이 처리된다."""
    codes = load_codes(_CODES)
    # 빈 설명 — 금액으로 폴백
    result_pos = classify("", 100000, codes)
    result_neg = classify("", -100000, codes)
    assert isinstance(result_pos, str) and len(result_pos) > 0
    assert isinstance(result_neg, str) and len(result_neg) > 0
    # 특수문자 포함 설명도 안전 처리
    result_special = classify("!@#$% ???", -50000, codes)
    assert isinstance(result_special, str)


def test_adv_accounting_codes_all_unique():
    """결함 2 회귀: 모든 계정과목 코드가 유일해야 한다."""
    data = json.loads(_CODES.read_text(encoding="utf-8"))
    codes = [v["code"] for k, v in data.items() if not k.startswith("_")]
    duplicates = [c for c in codes if codes.count(c) > 1]
    assert len(duplicates) == 0, (
        f"중복 코드 발견: {set(duplicates)} — 집계 시 항목이 합쳐지는 위험"
    )
    # 4자리 숫자 형식 검증
    for name, info in data.items():
        if name.startswith("_"):
            continue
        code = info["code"]
        assert len(code) == 4 and code.isdigit(), (
            f"{name}의 코드 '{code}'가 4자리 숫자 형식 아님"
        )


def test_boundary_account_code_aggregation_no_collision():
    """코드→이름 역매핑이 1:1이어야 집계 결과가 정확하다."""
    data = json.loads(_CODES.read_text(encoding="utf-8"))
    code_to_name: dict[str, str] = {}
    for name, info in data.items():
        if name.startswith("_"):
            continue
        code = info["code"]
        assert code not in code_to_name, (
            f"코드 {code}가 '{code_to_name[code]}'와 '{name}' 둘 다에 매핑 — "
            f"집계 오류 위험"
        )
        code_to_name[code] = name
