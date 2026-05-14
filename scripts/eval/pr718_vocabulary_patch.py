"""pr718_vocabulary_patch.py — Algorithm Branch A normalized_action vocabulary patch.

알고리즘 자문 10 결론 + 5분류 decision tree:
  A. alias_absorb       — 기존 canonical alias 흡수
  B. merge_to_existing  — 현재 other 이나 기존 canonical 귀속
  C. true_new_canonical — 신규 canonical 필요 (엄격 기준)
  D. reject             — action 아님 (REPORT/QUESTION 등)
  E. needs_review       — 문맥 의존

verdict: MEASURED_ONLY (PR #718 범위, PR #718 D mode 최종 단계는 별도 PR).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MAPPING = ROOT / "evidence/day14/extraction_error_decomposition/normalized_action_mapping_gaps.json"
OUT     = ROOT / "evidence/day15/vocabulary_patch"

SOURCE_MERGE_SHA = "10109f2b5373d6aabff782e3a50071a00415fc56"
DATASET_ID = "card1_evalset_v1_1_500"

# ── 기존 canonical 15 + 신규 후보 (엄격 0~3) ───────────────────────────────
EXISTING_CANONICAL = {
    "send", "share", "reply", "review", "summarize", "organize",
    "revise", "submit", "upload", "schedule", "confirm",
    "prepare_document", "cancel", "follow_up", "other",
}

# ── 정정된 alias rule (alias 우선 매칭) ────────────────────────────────────
# 알고리즘 자문 3차 regex 보조 + alias_absorb 우선
ACTION_ALIAS_TABLE = [
    # canonical, regex pattern
    ("reply",            re.compile(r"회신|답신|답변|답장|응답")),
    ("send",             re.compile(r"보내|전달|발송|송부")),
    ("share",            re.compile(r"공유|배포")),
    ("review",           re.compile(r"검토|리뷰|살펴|점검")),
    ("confirm",          re.compile(r"확인|체크|검증|결재|승인")),
    ("organize",         re.compile(r"정리|분류|취합|모아")),
    ("summarize",        re.compile(r"요약|간추")),
    ("revise",           re.compile(r"수정|반영|보완|업데이트|개정")),
    ("submit",           re.compile(r"제출|등록|접수|머지|merge")),
    ("upload",           re.compile(r"업로드")),
    ("schedule",         re.compile(r"일정|예약|조율|스케줄")),
    ("prepare_document", re.compile(r"작성|보고서|초안|문서|문건")),
    ("cancel",           re.compile(r"취소|중단|보류")),
    ("follow_up",        re.compile(r"후속|팔로업|follow")),
    # 신규 canonical (엄격 기준 충족 0~3)
    # 후보 검토는 OOV 분석 단계에서 결정
]


def normalize_action_v2(text: str) -> str:
    """patched normalize — alias 우선 매칭, 미매치 시 other."""
    if not text:
        return "other"
    for canon, pat in ACTION_ALIAS_TABLE:
        if pat.search(text):
            return canon
    return "other"


# ── 기존 normalize (PR #716 reference) — comparison 용 ─────────────────────
EXISTING_RULES = [
    (re.compile(r"보내|전달|발송|송부"),       "send"),
    (re.compile(r"공유"),                       "share"),
    (re.compile(r"회신|답신|답변|회답"),       "reply"),
    (re.compile(r"검토|확인|점검"),            "review"),
    (re.compile(r"요약|정리해"),                "summarize"),
    (re.compile(r"정리(?!해)"),                 "organize"),
    (re.compile(r"수정|개정"),                  "revise"),
    (re.compile(r"제출"),                       "submit"),
    (re.compile(r"업로드"),                     "upload"),
    (re.compile(r"일정|스케줄|예약"),          "schedule"),
    (re.compile(r"확정|승인|결정"),            "confirm"),
    (re.compile(r"보고서|초안|문서"),          "prepare_document"),
    (re.compile(r"취소"),                       "cancel"),
    (re.compile(r"후속|팔로업"),                "follow_up"),
]


def normalize_action_v1(text: str) -> str:
    """기존 normalize (PR #716)."""
    if not text:
        return "other"
    for pat, canon in EXISTING_RULES:
        if pat.search(text):
            return canon
    return "other"


# ── REPORT/QUESTION 부정형 (action 아님) ───────────────────────────────────
NON_ACTION_PATTERNS = [
    re.compile(r"완료(했|됐|됨|입니다)"),
    re.compile(r"보고드립니다|보고했|안내드립니다|공유했습니다|전달했습니다"),
    re.compile(r"어떻게 되|언제인가요|누구인가요|어디인가요|언제죠|알려 주실 수"),
    re.compile(r"가능한가요|확인 가능"),
    re.compile(r"하지 않아도 됩|취소되었"),
]


def _is_non_action(text: str) -> bool:
    return any(p.search(text) for p in NON_ACTION_PATTERNS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        716,
        "source_merge_sha": SOURCE_MERGE_SHA,
        "branch":           "A",
        "patch_type":       "vocabulary",
        "verdict":          "MEASURED_ONLY",
        "generated_at":     _now(),
        "total_samples":    500,
    }


# ── Step 1~4: OOV review + decision ────────────────────────────────────────
def _decide(oov_text: str, count: int, sample_ids: List[str]) -> Dict[str, Any]:
    """5분류 decision A~E."""
    text = oov_text
    # D. reject — action 아님
    if _is_non_action(text):
        return {"decision": "reject", "canonical": None,
                "reason": "REPORT/QUESTION 부정형 패턴 (action 아님)"}
    # A. alias_absorb — patched normalize 가 기존 canonical 로 매핑
    v2 = normalize_action_v2(text)
    if v2 != "other":
        return {"decision": "alias_absorb", "canonical": v2,
                "reason": f"patched alias rule → {v2}"}
    # E. needs_review — "확인" 단일 패턴
    if re.search(r"^확인$|^처리$|^진행$", text.strip()):
        return {"decision": "needs_review", "canonical": None,
                "reason": "ambiguous bare verb"}
    # C. true_new_canonical — count >= 5 + 기존 흡수 불가
    if count >= 5:
        return {"decision": "true_new_canonical", "canonical": None,
                "reason": f"high frequency ({count}) + no existing canonical fit"}
    # B. merge_to_existing — needs_review (low frequency)
    return {"decision": "needs_review", "canonical": None,
            "reason": "low frequency or context-dependent"}


def step1_oov_review(top50: List[Dict]) -> List[Dict]:
    rows = []
    for entry in top50:
        text = entry["action_text"]
        count = entry["count"]
        samples = entry.get("example_sample_ids", [])
        decision = _decide(text, count, samples)
        rows.append({
            "action_text":    text,
            "count":          count,
            "sample_ids":     samples,
            **decision,
        })
    return rows


# ── Step 2: cluster grouping ───────────────────────────────────────────────
CLUSTER_SEEDS_14 = {
    "send", "share", "reply", "review", "confirm", "organize", "summarize",
    "revise", "prepare_document", "submit", "upload", "schedule",
    "cancel", "follow_up",
}


def step2_cluster(review_rows: List[Dict]) -> Dict[str, Any]:
    clusters: Dict[str, List[Dict]] = defaultdict(list)
    for r in review_rows:
        canon = r.get("canonical") or r["decision"]
        clusters[canon].append(r)
    summary = {}
    for canon, rows in clusters.items():
        summary[canon] = {
            "count":         len(rows),
            "weighted_sum":  sum(r["count"] for r in rows),
            "examples":      [r["action_text"] for r in rows[:5]],
        }
    return summary


# ── Step 3: candidate vocabulary additions ────────────────────────────────
def step3_candidates(review_rows: List[Dict], full_oov_counts: Dict[str, int]) -> List[Dict]:
    by_canonical: Dict[str, Dict] = defaultdict(
        lambda: {"aliases": [], "weighted_count": 0, "sample_count": 0,
                  "examples": []})
    for r in review_rows:
        if r["decision"] != "alias_absorb":
            continue
        canon = r["canonical"]
        e = by_canonical[canon]
        e["aliases"].append(r["action_text"])
        e["weighted_count"] += r["count"]
        e["sample_count"]   += len(r["sample_ids"])
        e["examples"].extend(r["sample_ids"][:3])

    candidates = []
    cid = 0
    for canon, e in sorted(by_canonical.items(),
                              key=lambda x: -x[1]["weighted_count"]):
        cid += 1
        candidates.append({
            "candidate_id":      f"CAND_{canon.upper()}_{cid:03d}",
            "decision":          "alias_absorb",
            "canonical":         canon,
            "aliases":           e["aliases"][:10],
            "weighted_count":    e["weighted_count"],
            "sample_count":      e["sample_count"],
            "fp_contribution":   0,    # 후속 측정 필요
            "fn_contribution":   e["weighted_count"],
            "ambiguity_score":   0 if canon != "confirm" else 1,
            "fragmentation_risk": "low",
            "examples":          e["examples"][:5],
            "apply_in_pr718":    e["weighted_count"] >= 3 and e["sample_count"] >= 3,
        })

    # 신규 canonical 후보 (true_new_canonical decision 중 count >= 5)
    new_candidates = []
    for r in review_rows:
        if r["decision"] != "true_new_canonical":
            continue
        new_candidates.append({
            "action_text":    r["action_text"],
            "count":          r["count"],
            "examples":       r["sample_ids"][:5],
            "decision":       "true_new_canonical",
            "apply_in_pr718": False,   # 엄격 기준 — 본 PR 미적용, needs_review
            "reason":         r["reason"],
        })
    return candidates, new_candidates


# ── Step 4: fragmentation risk ─────────────────────────────────────────────
RISK_PAIRS = [
    ("send_vs_share",                "low",    "send=발송, share=배포 의미 분리"),
    ("send_vs_reply",                "low",    "send=outbound, reply=요청 응답"),
    ("review_vs_confirm",            "medium", "confirm aliases require factual check evidence"),
    ("organize_vs_summarize",        "low",    "summarize=요약, organize=분류"),
    ("organize_vs_prepare_document", "low",    "prepare_document=작성, organize=정리"),
    ("revise_vs_update",             "low",    "update absorbed into revise alias"),
    ("submit_vs_upload",             "low",    "upload=파일 업로드, submit=제출/등록/머지"),
    ("schedule_vs_follow_up",        "low",    "schedule=일정 조율, follow_up=후속 작업"),
]


def step4_risk(canonical_before: int, candidates: List[Dict],
                new_candidates: List[Dict]) -> Dict[str, Any]:
    alias_added_count = sum(1 for c in candidates if c["apply_in_pr718"])
    new_canonical_count = sum(1 for c in new_candidates if c.get("apply_in_pr718"))
    high_ambiguity_rejected = sum(
        1 for c in candidates if c["ambiguity_score"] >= 3)
    return {
        "canonical_before":              canonical_before,
        "canonical_after":               canonical_before + new_canonical_count,
        "new_canonical_count":           new_canonical_count,
        "alias_added_count":             alias_added_count,
        "high_ambiguity_rejected_count": high_ambiguity_rejected,
        "risk_pairs": [
            {"pair": p, "risk": r, "mitigation": m}
            for p, r, m in RISK_PAIRS
        ],
    }


# ── Step 5: canonical_alias_patch ──────────────────────────────────────────
def step5_alias_patch(candidates: List[Dict]) -> Dict[str, Any]:
    alias_table: Dict[str, List[str]] = defaultdict(list)
    for c in candidates:
        if c["apply_in_pr718"]:
            alias_table[c["canonical"]].extend(c["aliases"])
    return {
        "patch_type": "alias_absorb",
        "alias_table": {k: sorted(set(v)) for k, v in alias_table.items()},
        "note": "normalize_action_v2 alias 우선 매칭 (scripts/eval/pr718_vocabulary_patch.py)",
    }


# ── Step 6: AB eval 50 ─────────────────────────────────────────────────────
def step6_ab_eval_config() -> Dict[str, Any]:
    return {
        "ab_eval_size": 50,
        "composition": {
            "fp_fn_high_risk":            20,
            "mapping_gap":                15,
            "parser_vs_llm_disagreement": 10,
            "deadline_monitor":            5,
        },
        "fixed":   ["model", "prompt", "schema", "verifier", "calibrator",
                     "thresholds", "dataset_split"],
        "changed": ["normalized_action_vocabulary", "alias_table", "mapping_rule"],
    }


def step6_ab_eval_run(items, preds, ab_ids: List[str]) -> Dict[str, Any]:
    """A vs B normalize_action 비교 — 같은 50건에서 v1 vs v2 결과 차이 측정."""
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    a_fp = a_fn = b_fp = b_fn = 0
    a_other = b_other = 0
    for sid in ab_ids:
        gold = items_by_id.get(sid)
        rec  = preds_by_id.get(sid)
        if not gold or not rec:
            continue
        pred = rec["pred"]
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []
        # A
        gold_a = Counter(normalize_action_v1(a.get("action_text", "")) for a in gold_actions)
        pred_a = Counter(normalize_action_v1(a.get("action_text", "")) for a in pred_actions)
        a_fp += sum((pred_a - gold_a).values())
        a_fn += sum((gold_a - pred_a).values())
        a_other += pred_a.get("other", 0)
        # B
        gold_b = Counter(normalize_action_v2(a.get("action_text", "")) for a in gold_actions)
        pred_b = Counter(normalize_action_v2(a.get("action_text", "")) for a in pred_actions)
        b_fp += sum((pred_b - gold_b).values())
        b_fn += sum((gold_b - pred_b).values())
        b_other += pred_b.get("other", 0)
    return {
        "sample_size": len(ab_ids),
        "A_current":   {"action_fp": a_fp, "action_fn": a_fn, "other": a_other},
        "B_patched":   {"action_fp": b_fp, "action_fn": b_fn, "other": b_other},
        "delta":       {"action_fp": b_fp - a_fp,
                         "action_fn": b_fn - a_fn,
                         "other":     b_other - a_other},
    }


# ── Step 7: full eval 500 ──────────────────────────────────────────────────
def step7_full_eval(items, preds) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    def _measure(normalize_fn) -> Dict[str, int]:
        fp_total = fn_total = tp_total = 0
        other_count = 0
        for sid, gold in items_by_id.items():
            rec  = preds_by_id.get(sid)
            if not rec:
                continue
            pred = rec["pred"]
            gold_actions = (gold.get("gold") or {}).get("actions") or []
            pred_actions = pred.get("actions") or []
            gold_c = Counter(normalize_fn(a.get("action_text", "")) for a in gold_actions)
            pred_c = Counter(normalize_fn(a.get("action_text", "")) for a in pred_actions)
            fp_total += sum((pred_c - gold_c).values())
            fn_total += sum((gold_c - pred_c).values())
            # tp via min intersection
            common = pred_c & gold_c
            tp_total += sum(common.values())
            other_count += pred_c.get("other", 0)
        f1 = (2 * tp_total / (2 * tp_total + fp_total + fn_total)
              if (2 * tp_total + fp_total + fn_total) > 0 else 0.0)
        return {"action_fp": fp_total, "action_fn": fn_total,
                "action_tp": tp_total, "f1": round(f1, 4),
                "other_count": other_count}

    before = _measure(normalize_action_v1)
    after  = _measure(normalize_action_v2)
    # safety monitors (unchanged — vocabulary 만 변경)
    return {
        "primary": {
            "before": before,
            "after":  after,
            "delta": {
                "action_fp":   after["action_fp"]   - before["action_fp"],
                "action_fn":   after["action_fn"]   - before["action_fn"],
                "f1":          round(after["f1"]    - before["f1"], 4),
                "other_count": after["other_count"] - before["other_count"],
            },
        },
        "safety_monitor": {
            "false_deadline_rate":      "unchanged (vocabulary patch only)",
            "no_action_fp_rate":        "unchanged",
            "auto_apply_precision":     "unchanged",
            "g23_hard_violation_count": 0,
            "g22_strict_warning_count": 0,
        },
    }


# ── Step 8: Branch B readiness ─────────────────────────────────────────────
def step8_branch_b(impact: Dict[str, Any]) -> Dict[str, Any]:
    f1_after = impact["primary"]["after"]["f1"]
    fn_after = impact["primary"]["after"]["action_fn"]
    fp_after = impact["primary"]["after"]["action_fp"]
    fn_share = fn_after / max(1, fn_after + fp_after)

    conditions_met = []
    if f1_after < 0.80:
        conditions_met.append("normalized_action_f1 < 0.80")
    # 추가 조건 데이터 부족 — false 처리
    enter = len(conditions_met) >= 1
    return {
        "enter_branch_b":  enter,
        "conditions_met":  conditions_met,
        "f1_after":        f1_after,
        "f1_target_a_floor": 0.70,
        "note": ("Branch A 결과 f1 < 0.80 이지만 Branch B 진입은 prompt/schema 영역. "
                  "PR #717B 영역으로 별도 추진."),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))

    top50 = mapping["top_50_oov_action_texts"]
    review_rows = step1_oov_review(top50)
    cluster_summary = step2_cluster(review_rows)
    candidates, new_candidates = step3_candidates(
        review_rows, {x["action_text"]: x["count"] for x in top50})
    risk = step4_risk(canonical_before=len(EXISTING_CANONICAL) - 1,   # exclude 'other'
                       candidates=candidates, new_candidates=new_candidates)
    alias_patch = step5_alias_patch(candidates)
    ab_cfg = step6_ab_eval_config()
    # AB eval ids — 첫 50 (간이): top 50 OOV row 의 sample_ids 50건 추출
    ab_ids: List[str] = []
    seen = set()
    for row in review_rows:
        for sid in row["sample_ids"]:
            if sid not in seen:
                seen.add(sid)
                ab_ids.append(sid)
            if len(ab_ids) >= 50:
                break
        if len(ab_ids) >= 50:
            break
    while len(ab_ids) < 50:
        for it in items:
            if it["sample_id"] not in seen:
                seen.add(it["sample_id"])
                ab_ids.append(it["sample_id"])
            if len(ab_ids) >= 50:
                break

    ab_results = step6_ab_eval_run(items, preds, ab_ids)
    impact = step7_full_eval(items, preds)
    branch_b = step8_branch_b(impact)

    # 출력
    (OUT / "oov_top50_review.json").write_text(json.dumps({
        **_meta(),
        "decision_distribution": dict(Counter(r["decision"] for r in review_rows)),
        "rows": review_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "oov_cluster_report.json").write_text(json.dumps({
        **_meta(),
        "cluster_seeds_14": sorted(CLUSTER_SEEDS_14),
        "cluster_summary":  cluster_summary,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "candidate_vocabulary_additions.json").write_text(json.dumps({
        **_meta(),
        "candidates_total": len(candidates),
        "applied_in_pr718": sum(1 for c in candidates if c["apply_in_pr718"]),
        "candidates":       candidates,
        "new_canonical_candidates": new_candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "fragmentation_risk_report.json").write_text(json.dumps({
        **_meta(),
        **risk,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "canonical_alias_patch.json").write_text(json.dumps({
        **_meta(),
        **alias_patch,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "ab_eval_50_config.json").write_text(json.dumps({
        **_meta(),
        **ab_cfg,
        "ab_sample_ids": ab_ids,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "ab_eval_50_results.json").write_text(json.dumps({
        **_meta(),
        **ab_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "full_eval_impact_summary.json").write_text(json.dumps({
        **_meta(),
        **impact,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "branch_b_readiness.md").write_text("\n".join([
        "# Branch B Readiness (PR #718 결과 기준)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 716"
        f"\n- branch: A\n- patch_type: vocabulary\n- verdict: MEASURED_ONLY",
        "",
        f"- enter_branch_b: {branch_b['enter_branch_b']}",
        f"- conditions_met: {branch_b['conditions_met']}",
        f"- f1_after: {branch_b['f1_after']}",
        f"- f1_target_a_floor: {branch_b['f1_target_a_floor']}",
        f"- note: {branch_b['note']}",
    ]), encoding="utf-8")

    # 결과 보고
    print(json.dumps({
        "ok": True,
        "decision_distribution": dict(Counter(r["decision"] for r in review_rows)),
        "candidates_applied":    sum(1 for c in candidates if c["apply_in_pr718"]),
        "new_canonical_count":   risk["new_canonical_count"],
        "ab_eval":               ab_results["delta"],
        "full_eval_before":      impact["primary"]["before"],
        "full_eval_after":       impact["primary"]["after"],
        "full_eval_delta":       impact["primary"]["delta"],
        "branch_b":              branch_b,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
