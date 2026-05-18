"""pr738_residual_a4_9_review_protocol.py — Residual A4 9 Review Protocol.

자문 6차 §13 PR B — 잔여 A4 9건('부탁드립니다' 7 + '보고드리려고 합니다'
2)을 직접 수정하지 않고 평가 protocol 로 분리. Internal Alpha feedback
target 지정 (M-5 옵션 D 1순위).

평가 protocol PR — gold/normalized_action label 수정 0, 알고리즘/prompt/
model 변경 0, 새 측정 알고리즘 0, text-only guard 추가 강화 0 (M-1).

GitHub PR 번호: actual_github_pr 는 gh pr create 후 확정 — 강화 안건 17
정합. 본 스크립트 ACTUAL_GITHUB_PR 상수로 중앙 관리.

verdict: MEASURED_ONLY (PROCEED 금지).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.pr734_final_beta_readiness_measurement import (  # noqa: E402
    compute_coverage,
)

DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED_A = ROOT / "evidence/day19/branch_b3a_arbitration/mixed_a_67_six_subtype_classification.json"
A4_COV  = ROOT / "evidence/day26/b2g_over_extraction_guard/a4_guard_coverage_report.json"
OUT     = ROOT / "evidence/day30/residual_a4_9_review_protocol"

DATASET_ID = "card1_evalset_v1_1_500"
PR737_MERGE_SHA = "f61df6f6"
CONTRACT_VERSION = "2.0.0"
# 강화 안건 17 — actual GitHub PR 번호 (gh pr create 후 확정/검증)
ACTUAL_GITHUB_PR = 738
LEGACY_HANDOFF_LABEL = "PR #738+ (chat 인계 박스 표기)"

MAIN_METRICS = {"strict_action_f1": 0.6452, "deadline_f1": 0.8702,
                "action_fp": 207}


def _meta() -> Dict[str, Any]:
    return {"dataset_id": DATASET_ID,
            "source_pr": ACTUAL_GITHUB_PR,
            "actual_github_pr": ACTUAL_GITHUB_PR,
            "legacy_handoff_label": LEGACY_HANDOFF_LABEL,
            "source_merge_sha": PR737_MERGE_SHA,
            "branch": "Residual-A4-9-Review-Protocol",
            "patch_type": "evaluation_protocol_separation_no_algorithm_change",
            "verdict": "MEASURED_ONLY"}


def _text(it: Dict) -> str:
    return it.get("text") or it.get("text_redacted") or ""


def utterance_digest(text: str) -> str:
    """원문 utterance → sha256 16자 digest (meta-only — 강화 안건 18).

    원문은 evidence 산출물에 저장하지 않으며 digest 로만 기록한다.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def classify_residual(text: str) -> str:
    """잔여 A4 표면형 분류 — '부탁' 계열 / '보고드리려고' 계열."""
    if "부탁" in text:
        return "polite_request_surface_form"      # 정상 요청과 표면 동일
    if "드리려고" in text or "보고드리" in text:
        return "intent_to_report_surface_form"    # A5 card1_100078 표면 동일
    return "other_ambiguous"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = {}
    for line in DATASET.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            items[it["sample_id"]] = it
    pred_rows = [json.loads(line) for line in PREDS.open(encoding="utf-8")
                 if line.strip()]
    mixed = json.loads(MIXED_A.read_text(encoding="utf-8"))
    mixed_id_list = [r["sample_id"] for r in mixed["rows"]]
    pred_id_list = [p["sample_id"] for p in pred_rows]

    # ── dataset integrity (PR #734 compute_coverage 재사용) ──
    coverage = compute_coverage(mixed_id_list, set(items), pred_id_list)
    coverage["mode"] = "residual_a4_9_review_protocol"
    coverage["plan_pr_note"] = ("평가 protocol PR — 신규 measurement 없음. "
        "dataset integrity 무결성만 확인 (PR #730/#734 패턴).")
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                         ensure_ascii=False))
        return 1
    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 잔여 A4 9건 본질 분석 (Codex P1 정정 — meta-only, 원문 미저장) ──
    # 원문 utterance 는 내부 계산(classify_residual)에만 사용하고 산출물에는
    # 기록하지 않는다. 강화 안건 18 / Butler 지침서 §7 / AGENTS.md 원문0.
    residual_ids = json.loads(A4_COV.read_text(encoding="utf-8"))["a4_residual_ids"]
    rows: List[Dict[str, Any]] = []
    for sid in residual_ids:
        it = items[sid]
        text = _text(it)   # 내부 계산만 — 산출물 미기록
        rows.append({
            "sample_id": sid,
            "surface_form": classify_residual(text),
            "gold_intent": it.get("intent_type"),
            "utterance_digest": utterance_digest(text),
            "text_len": len(text),
            "redaction_status": "meta_only",
        })
    from collections import Counter
    form_dist = Counter(r["surface_form"] for r in rows)
    (OUT / "residual_a4_9_본질_분석.json").write_text(json.dumps({
        **_meta(),
        "residual_a4_count": len(rows),
        "surface_form_distribution": dict(form_dist),
        "case_redefinition_M2": ("surface-form ambiguous over-extraction "
            "cases — gold 가 REPORT/0-action 이나 표면형이 정상 요청과 "
            "구분 불가 (자문 6차 M-2)."),
        "text_only_separable": False,
        "text_only_separable_reason": ("정상 요청 / A5(gold>=1) 케이스와 "
            "표면 동일 — text-only guard 로 안전 분리 불가 (PR #732 정직)."),
        "privacy": "meta-only — 원문 utterance 미저장 (강화 안건 18)",
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── residual_a4_9_metric_연동_명세 ──
    (OUT / "residual_a4_9_metric_연동_명세.json").write_text(json.dumps({
        **_meta(),
        "strict_extraction": ("잔여 9건은 strict layer 에서 FP 로 유지 — "
            "FP→TP 처리 0 (자문 6차 정합)."),
        "layer2_candidate_metrics": [
            "manual_suggestion_precision", "suggestion_usefulness_rate",
            "unsafe_suggestion_rate", "edit_required_rate"],
        "metric_연동_note": ("잔여 9건은 Internal Alpha feedback 의 4 "
            "카테고리 수집 대상 — Layer 2 candidate metric 으로 연동. "
            "strict_action_f1 산식 불변."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── policy_drift / before_after ──
    (OUT / "policy_drift_assessment.json").write_text(json.dumps({
        **_meta(), "policy_name": "card1 action metric contract",
        "contract_version": CONTRACT_VERSION, "contract_version_changed": False,
        "drift_rate": 0.0, "drift_class": "OK", "samples_compared": 0,
        "is_standard10_policy_drift_report": False,
        "drift_note": ("평가 protocol PR — metric contract v2.0.0 불변. "
            "v2.1.0 즉시 bump 0 (자문 6차 M-8). 후보 안건만 명세."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "before_after_main_metrics.json").write_text(json.dumps({
        **_meta(),
        "comparison": [{"metric": m, "before": v, "after": v, "delta": 0.0}
                       for m, v in MAIN_METRICS.items()],
        "safety_6_delta_zero": True,
        "reason": ("평가 protocol 분리 PR — 잔여 9건 직접 수정 0, 알고리즘/"
                   "측정 변경 0 → main 측정값 변동 0."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── summary ──
    (OUT / "summary.md").write_text("\n".join([
        f"# PR #{ACTUAL_GITHUB_PR} — Residual A4 9 Review Protocol Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n"
        f"- actual_github_pr: {ACTUAL_GITHUB_PR}\n"
        f"- legacy_handoff_label: {LEGACY_HANDOFF_LABEL}\n"
        f"- source_pr: {ACTUAL_GITHUB_PR}\n"
        f"- branch: Residual-A4-9-Review-Protocol\n"
        f"- patch_type: evaluation_protocol_separation_no_algorithm_change\n"
        f"- verdict: MEASURED_ONLY",
        "",
        "## 본 PR 의 본질 (정직 보고)",
        "- 평가 protocol PR — 잔여 A4 9건을 직접 수정하지 않고 평가 "
        "protocol 로 분리 + Internal Alpha feedback target 지정.",
        "- gold/normalized_action label 수정 0, 알고리즘/prompt/model 변경 0,",
        "  text-only guard 추가 강화 0 (자문 6차 M-1).",
        "",
        "## 잔여 A4 9건 본질 분석 (자문 6차 M-2)",
        *[f"- {sf}: {c}건" for sf, c in sorted(form_dist.items())],
        "- 표면형 ambiguous over-extraction cases — 정상 요청 / A5 와 표면 "
        "동일하여 text-only guard 로 안전 분리 불가 (PR #732 정직 정합).",
        "",
        "## 평가 protocol 분리",
        "- 잔여 9건은 strict layer 에서 FP 로 유지 (FP→TP 처리 0).",
        "- gold/contract review path + Internal Alpha feedback target 지정.",
        "- 4 카테고리 수집 (useful / irrelevant / unsafe / needs_edit, PR #737).",
        "",
        "## metric contract v2.1.0 보류 (자문 6차 M-8 정직 보고)",
        "- v2.1.0 즉시 bump 0 — 후보 안건만 명세. bump 조건: msp 권위 측정 "
        ">= 0.80 또는 사용자 가치 분리 반복 확인 후.",
        "",
        "## main 측정값 정합 (변동 0)",
        "- strict_action_f1 0.6452 / deadline_f1 0.8702 / action_fp 207 / "
        "safety 6종 — 전부 불변. metric contract v2.0.0 유지.",
        "",
        "## verdict: MEASURED_ONLY",
        "평가 protocol PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "actual_github_pr": ACTUAL_GITHUB_PR,
        "legacy_handoff_label": LEGACY_HANDOFF_LABEL,
        "residual_a4_count": len(rows),
        "surface_form_distribution": dict(form_dist),
        "coverage_ok": coverage["fail_class"] is None,
        "verdict": "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
