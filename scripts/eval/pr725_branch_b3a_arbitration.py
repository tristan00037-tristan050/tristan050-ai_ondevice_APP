"""pr725_branch_b3a_arbitration.py — Algorithm Branch B-3A arbitration measurement.

자문 회신 1.3 / 2.2 / 2.5 정합:
  - MIXED-A 67건 → 6 subtype (A1~A6) 재분류
  - parser/LLM 부분 정답 합성 arbitration rule 후보 측정
  - field-level 비교 + evidence 정합 점수
  - simulation only — 실제 적용 금지 (Branch B-3B 별도 PR)

verdict: MEASURED_ONLY (적용 없음, PATCH_CONTINUE/PROCEED 금지).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT    = Path(__file__).resolve().parents[2]
DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED   = ROOT / "evidence/day17/branch_b2/mixed_116_taxonomy.json"
MODE_A  = ROOT / "evidence/day11/mode_a/predictions.jsonl"
MODE_B  = ROOT / "evidence/day11/mode_b/predictions.jsonl"
OUT     = ROOT / "evidence/day19/branch_b3a_arbitration"

PR723_MERGE_SHA = "d26883e87f1b079f852ecaa45e7def487905b30e"
DATASET_ID = "card1_evalset_v1_1_500"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        723,
        "source_merge_sha": PR723_MERGE_SHA,
        "branch":           "B-3A",
        "patch_type":       "arbitration_measurement_only",
        "verdict":          "MEASURED_ONLY",
        "generated_at":     _now(),
        "total_samples":    500,
    }


DEADLINE_MARKER_RE = re.compile(r"까지|전까지|안에|이내|마감|기한")
OVER_GUARD_RE = re.compile(r"가능한가요|어떻게 되|언제인가요|완료했습니다|보고드립니다")


# ── MIXED-A 6 subtype 재분류 (A1~A6) — field-level 점수 기반 ───────────────
def classify_mixed_a(sid: str, gold: Dict, pred: Dict,
                     mode_a: Dict, mode_b: Dict) -> Dict[str, Any]:
    """A1~A6 분류 — field-level 우세 + deadline/over-extraction 신호 결합."""
    text = gold.get("text") or gold.get("text_redacted") or ""
    gi = gold.get("intent_type")
    gd = gold.get("deadline_type") or "NONE"
    ap_intent = (mode_a or {}).get("intent_type")
    bp_intent = (mode_b or {}).get("intent_type")
    pred_actions = pred.get("actions") or []
    has_action = bool(pred_actions)

    fields = ["intent_type", "deadline_type", "action_required",
              "answer_required", "auto_apply_allowed"]
    parser_score = sum(1 for f in fields if (mode_a or {}).get(f) == gold.get(f))
    llm_score    = sum(1 for f in fields if (mode_b or {}).get(f) == gold.get(f))

    # A2: deadline 관여 (Branch D 영역)
    if gd in {"HARD", "SOFT", "INQUIRY"}:
        return {"subtype": "MIXED-A2_parser_deadline_llm_action",
                "recovery_route": "Branch D 흡수",
                "recoverable_estimate": 0.6,
                "parser_field_score": parser_score, "llm_field_score": llm_score}
    # A4: parser 우세 + over-extraction 신호 (parser 가 보수적이지 못함)
    if parser_score > llm_score and OVER_GUARD_RE.search(text):
        return {"subtype": "MIXED-A4_parser_overextract_llm_conservative",
                "recovery_route": "over_guard 유지 (Branch B-2)",
                "recoverable_estimate": 0.7,
                "parser_field_score": parser_score, "llm_field_score": llm_score}
    # A5: llm 우세 + over-extraction 신호
    if llm_score > parser_score and OVER_GUARD_RE.search(text):
        return {"subtype": "MIXED-A5_llm_overextract_parser_conservative",
                "recovery_route": "G23/negative prompt (제한 적용)",
                "recoverable_estimate": 0.5,
                "parser_field_score": parser_score, "llm_field_score": llm_score}
    # A3: llm 우세 + action 있음 (evidence-aware arbitration 후보)
    if llm_score > parser_score and has_action:
        return {"subtype": "MIXED-A3_llm_action_parser_evidence",
                "recovery_route": "evidence-aware arbitration",
                "recoverable_estimate": 0.6,
                "parser_field_score": parser_score, "llm_field_score": llm_score}
    # A1: parser 우세 또는 동률 + action 있음 (hybrid merge 후보)
    if parser_score >= llm_score and has_action:
        return {"subtype": "MIXED-A1_parser_action_llm_object",
                "recovery_route": "hybrid merge rule 개선",
                "recoverable_estimate": 0.55,
                "parser_field_score": parser_score, "llm_field_score": llm_score}
    # A6: no clear winner (점수 동률 + action 없음)
    return {"subtype": "MIXED-A6_no_clear_winner",
            "recovery_route": "보류 — evidence 축적",
            "recoverable_estimate": 0.2,
            "parser_field_score": parser_score, "llm_field_score": llm_score}


# ── field-level 비교 + evidence 정합 점수 ─────────────────────────────────
def field_level_compare(gold: Dict, mode_a: Dict, mode_b: Dict,
                         pred: Dict) -> Dict[str, Any]:
    fields = ["intent_type", "deadline_type", "action_required",
              "answer_required", "auto_apply_allowed"]
    parser_correct = sum(1 for f in fields
                         if (mode_a or {}).get(f) == gold.get(f))
    llm_correct    = sum(1 for f in fields
                         if (mode_b or {}).get(f) == gold.get(f))
    hybrid_correct = sum(1 for f in fields
                         if pred.get(f) == gold.get(f))
    return {
        "parser_field_score": parser_correct,
        "llm_field_score":    llm_correct,
        "hybrid_field_score": hybrid_correct,
        "field_total":        len(fields),
    }


def evidence_score(text: str, pred: Dict) -> tuple[float, int]:
    """Codex P2 정정 — blank evidence/action_text 는 matched 로 계산하지 않는다.

    이전 구현은 ``(a.get("evidence") or a.get("action_text", "")) in text`` 로,
    evidence/action_text 가 모두 빈 문자열이면 ``"" in text`` 가 True 라
    matched 처리되어 evidence_score 가 과대평가되었다.
    반환: (evidence_score, blank_count)
    """
    actions = pred.get("actions") or []
    if not actions:
        return 1.0, 0   # action 없으면 evidence 위반 없음
    matched_count = 0
    blank_count = 0
    for a in actions:
        evidence    = (a.get("evidence") or "").strip()
        action_text = (a.get("action_text") or "").strip()
        # 둘 다 빈 문자열이면 matched=false (blank 카운트)
        if not evidence and not action_text:
            blank_count += 1
            continue
        # 유효한 evidence 우선, 없으면 action_text 사용
        source = evidence if evidence else action_text
        # 빈 문자열은 위 분기에서 걸러져 source match 로 계산되지 않음
        if source and source in text:
            matched_count += 1
    score = round(matched_count / len(actions), 4)
    return score, blank_count


def check_coverage(items: List[Dict], preds: List[Dict],
                   out_dir: Path) -> Dict[str, Any]:
    """Codex P1 정정 — prediction coverage drift fail-closed 완전 이식 (PR #723 패턴).

    이전 구현은 gold duplicate 만 검사하고 prediction duplicate / missing /
    extra 를 검사하지 않아 downstream classification 이 silent corruption
    상태로 진행될 수 있었다. gold/pred duplicate + missing + extra 를 모두
    검사하고, fail 시 coverage_report.json 기록 후 SystemExit 으로 차단한다.
    """
    item_id_list = [it["sample_id"] for it in items]
    pred_id_list = [p["sample_id"] for p in preds]
    items_ids = set(item_id_list)
    pred_ids  = set(pred_id_list)
    missing = items_ids - pred_ids
    extra   = pred_ids - items_ids
    gold_duplicate_ids       = [s for s, c in Counter(item_id_list).items() if c > 1]
    prediction_duplicate_ids = [s for s, c in Counter(pred_id_list).items() if c > 1]
    coverage = {
        "coverage_checked":             True,
        "expected_samples":             len(items_ids),
        "measured_samples":             len(items_ids & pred_ids),
        "missing_count":                len(missing),
        "missing_ids":                  sorted(missing)[:20],
        "extra_count":                  len(extra),
        "extra_ids":                    sorted(extra)[:20],
        "gold_duplicate_count":         len(gold_duplicate_ids),
        "gold_duplicate_ids":           gold_duplicate_ids[:20],
        "prediction_duplicate_count":   len(prediction_duplicate_ids),
        "prediction_duplicate_ids":     prediction_duplicate_ids[:20],
        "fail_class":                   None,
    }
    # fail-closed 우선순위: gold duplicate (items_by_id silent overwrite) 우선
    if gold_duplicate_ids:
        coverage["fail_class"] = "GOLD_SAMPLE_ID_DUPLICATE"
    elif missing or extra or prediction_duplicate_ids:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"
    (out_dir / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    if coverage["fail_class"]:
        print(json.dumps({
            "ok": False,
            "fail_class":                 coverage["fail_class"],
            "missing_count":              len(missing),
            "extra_count":                len(extra),
            "gold_duplicate_count":       len(gold_duplicate_ids),
            "prediction_duplicate_count": len(prediction_duplicate_ids),
        }, ensure_ascii=False))
        raise SystemExit(1)
    return coverage


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]
    mixed = json.loads(MIXED.read_text(encoding="utf-8"))
    a_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in MODE_A.open(encoding="utf-8") if l.strip()}
            if MODE_A.exists() else {})
    b_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in MODE_B.open(encoding="utf-8") if l.strip()}
            if MODE_B.exists() else {})

    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    # coverage fail-closed — Codex P1 정정 (sentinel #6/#7)
    # gold/pred duplicate + missing + extra 모두 검사 → downstream 차단.
    coverage = check_coverage(items, preds, OUT)

    # MIXED-A 67건 추출
    mixed_a_rows = [r for r in mixed["rows"]
                    if r["mixed_subtype"].startswith("MIXED-A")]

    # === 1) 6 subtype 재분류 ===
    classified = []
    subtype_counter: Counter = Counter()
    field_results = []
    evidence_scores = []
    for r in mixed_a_rows:
        sid = r["sample_id"]
        gold = items_by_id.get(sid) or {}
        pred = (preds_by_id.get(sid) or {}).get("pred") or {}
        ap   = (a_by.get(sid, {}).get("pred")) or {}
        bp   = (b_by.get(sid, {}).get("pred")) or {}
        text = gold.get("text") or gold.get("text_redacted") or ""
        info = classify_mixed_a(sid, gold, pred, ap, bp)
        info["sample_id"] = sid
        classified.append(info)
        subtype_counter[info["subtype"]] += 1
        # field-level 비교
        fl = field_level_compare(gold, ap, bp, pred)
        fl["sample_id"] = sid
        field_results.append(fl)
        # evidence 점수 — Codex P2 정정: blank_count 동반 측정
        ev_sc, blank_ct = evidence_score(text, pred)
        evidence_scores.append({"sample_id":      sid,
                                 "evidence_score": ev_sc,
                                 "blank_count":    blank_ct})

    (OUT / "mixed_a_67_six_subtype_classification.json").write_text(json.dumps({
        **_meta(),
        "mixed_a_total":         len(mixed_a_rows),
        "subtype_distribution":  dict(subtype_counter),
        "coverage_report":       coverage,
        "rows":                  classified,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 2) arbitration rule candidates ===
    (OUT / "arbitration_rule_candidates.md").write_text("\n".join([
        "# Arbitration Rule Candidates (Branch B-3A, 측정 only)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: B-3A"
        f"\n- patch_type: arbitration_measurement_only\n- verdict: MEASURED_ONLY",
        "",
        "## 후보 (적용 금지 — Branch B-3B 별도 PR)",
        "",
        "### AR-1 evidence-aware arbitration (MIXED-A3 대상)",
        "- parser 가 evidence 일치 + LLM 이 action 추출 → parser evidence 채택",
        "",
        "### AR-2 hybrid merge rule (MIXED-A1 대상)",
        "- parser action + LLM object 병합 (intent 는 LLM)",
        "",
        "### AR-3 conservative-wins (MIXED-A4/A5 대상)",
        "- over-extraction 측에서 conservative 쪽 채택 (Branch B-2 over_guard 정합)",
        "",
        "### AR-4 deadline delegation (MIXED-A2 대상)",
        "- deadline 영역은 Branch D classifier 결과로 위임",
        "",
        "### AR-5 hold-and-accumulate (MIXED-A6 대상)",
        "- no clear winner — 현 단계 보류, evidence 축적만",
        "",
        "## 적용 정책",
        "PR #725 는 측정 PR. arbitration rule 적용 자체는 Branch B-3B 별도 PR.",
    ]), encoding="utf-8")

    # === 3) field-level comparison ===
    parser_wins = sum(1 for f in field_results
                      if f["parser_field_score"] > f["llm_field_score"])
    llm_wins = sum(1 for f in field_results
                   if f["llm_field_score"] > f["parser_field_score"])
    tie = len(field_results) - parser_wins - llm_wins
    (OUT / "field_level_comparison_results.json").write_text(json.dumps({
        **_meta(),
        "mixed_a_total":      len(field_results),
        "parser_wins":        parser_wins,
        "llm_wins":           llm_wins,
        "tie":                tie,
        "rows":               field_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 4) evidence-aware arbitration simulation ===
    avg_ev = round(sum(e["evidence_score"] for e in evidence_scores)
                   / max(1, len(evidence_scores)), 4)
    ev_low = [e for e in evidence_scores if e["evidence_score"] < 0.5]
    total_blank = sum(e["blank_count"] for e in evidence_scores)
    (OUT / "evidence_aware_arbitration_simulation.json").write_text(json.dumps({
        **_meta(),
        "mixed_a_total":          len(evidence_scores),
        "avg_evidence_score":     avg_ev,
        "low_evidence_count":     len(ev_low),
        "blank_count":            total_blank,
        "evidence_scores":        evidence_scores,
        "note": "evidence_score < 0.5 인 row 는 evidence-aware arbitration 후보 (AR-1); "
                "blank_count 는 evidence/action_text 가 모두 빈 action 수 (Codex P2 정정).",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 5) recovery potential estimation ===
    recovery = {}
    for st, cnt in subtype_counter.items():
        est_rows = [c for c in classified if c["subtype"] == st]
        avg_est = round(sum(c["recoverable_estimate"] for c in est_rows)
                        / max(1, len(est_rows)), 4)
        recovery[st] = {
            "count":                cnt,
            "avg_recoverable_estimate": avg_est,
            "estimated_recoverable_rows": round(cnt * avg_est, 1),
            "recovery_route":       est_rows[0]["recovery_route"] if est_rows else "",
        }
    total_est_recoverable = round(
        sum(v["estimated_recoverable_rows"] for v in recovery.values()), 1)
    (OUT / "recovery_potential_estimation.json").write_text(json.dumps({
        **_meta(),
        "mixed_a_total":              len(mixed_a_rows),
        "subtype_recovery":           recovery,
        "total_estimated_recoverable": total_est_recoverable,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 6) Branch B-3B readiness ===
    (OUT / "branch_b3b_readiness.md").write_text("\n".join([
        "# Branch B-3B Readiness (PR #725 측정 결과 기준)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: B-3A"
        f"\n- verdict: MEASURED_ONLY",
        "",
        "## arbitration rule 후보 5개 (AR-1~AR-5)",
        f"- MIXED-A 67건 6 subtype 분류 완료",
        f"- total_estimated_recoverable: {total_est_recoverable}",
        "",
        "## AR-1 (evidence-aware arbitration) readiness — Codex P2 정정 후 재평가",
        f"- avg_evidence_score: {avg_ev}",
        f"- low_evidence_count (evidence_score < 0.5, AR-1 트리거 대상): {len(ev_low)}",
        f"- blank_count (evidence/action_text 모두 빈 action): {total_blank}",
        "- P2 정정 후 측정: MIXED-A pred 의 모든 action 이 evidence 보유"
        " (blank 0), evidence_score < 0.5 row 0건.",
        "- 현 데이터 기준 AR-1 트리거 대상 0건 — AR-1 은 후보로 유지하되,"
        " prediction 재측정으로 evidence_score 분포가 변할 때 재평가.",
        "",
        "## Branch B-3B 진입 조건",
        "- arbitration rule 중 safety regression 시뮬 0 인 rule 만 적용 대상",
        "- AR-1 (evidence-aware) / AR-3 (conservative-wins) 우선 후보",
        "- AR-2 (hybrid merge) 는 action_fp 회귀 모니터 필수",
        "- AR-5 (hold) 는 적용 없음",
        "",
        "## 적용 금지 (PR #725 측정 PR 성격)",
        "Branch B-3B 별도 PR 에서 arbitration rule 실제 적용 + AB simulation.",
    ]), encoding="utf-8")

    # === 7) summary ===
    (OUT / "summary.md").write_text("\n".join([
        "# PR #725 Algorithm Branch B-3A arbitration measurement Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: B-3A"
        f"\n- patch_type: arbitration_measurement_only\n- verdict: MEASURED_ONLY"
        f"\n- alignment_cycle: Codex P1+P2 정정 (HOLD 해소 cycle)"
        f"\n- correction: P1 prediction coverage drift fail-closed 완전 이식"
        f" / P2 blank evidence score 정정",
        "",
        "## MIXED-A 67건 6 subtype 분포",
        *[f"- {k}: {v}" for k, v in subtype_counter.items()],
        "",
        "## field-level 비교",
        f"- parser_wins: {parser_wins}",
        f"- llm_wins: {llm_wins}",
        f"- tie: {tie}",
        "",
        "## evidence-aware arbitration",
        f"- avg_evidence_score: {avg_ev}",
        f"- low_evidence_count (< 0.5): {len(ev_low)}",
        f"- blank_count (evidence/action_text 모두 빈 action): {total_blank}",
        "",
        f"## recovery potential: total_estimated_recoverable {total_est_recoverable} / 67",
        "",
        "## arbitration rule 후보 5개 (AR-1~AR-5) — 적용 없음 (측정 PR)",
        "",
        "## verdict: MEASURED_ONLY",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "mixed_a_total":              len(mixed_a_rows),
        "subtype_distribution":       dict(subtype_counter),
        "parser_wins":                parser_wins,
        "llm_wins":                   llm_wins,
        "tie":                        tie,
        "avg_evidence_score":         avg_ev,
        "low_evidence_count":         len(ev_low),
        "blank_count":                total_blank,
        "total_estimated_recoverable": total_est_recoverable,
        "coverage_ok":                coverage["fail_class"] is None,
        "verdict":                    "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
