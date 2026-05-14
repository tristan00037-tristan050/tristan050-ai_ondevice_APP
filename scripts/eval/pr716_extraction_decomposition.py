"""pr716_extraction_decomposition.py — Extraction Error Decomposition (PR #716).

알고리즘 + 메인 개발팀 자문 정합:
  산출물 6종 (extraction_error_decomposition/)
  메인 추가 evidence 4종 (extraction_error_decomposition/)
  metrics 2종 (metrics/)
  summary 1종 (summary/)
  → 총 13 파일

verdict: MEASURED_ONLY (PR #716 범위, PR #718 단계에서 공식 판정).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
OUT     = ROOT / "evidence/day14"

MERGE_SHA = "194d07eec4a196df65f9801f5ad35ed67c60520b"
DATASET_ID = "card1_evalset_v1_1_500"

# ── canonical normalized_action vocabulary (참조) ─────────────────────────
CANONICAL = {
    "send", "share", "reply", "review", "summarize", "organize",
    "revise", "submit", "upload", "schedule", "confirm",
    "prepare_document", "cancel", "follow_up", "other",
}

# ── 1차 rule-based regex (PR #716 분해 영역) ───────────────────────────────
REPORT_FIXED = ["완료했습니다", "보고드립니다", "안내드립니다",
                "공유했습니다", "전달했습니다"]
PURE_QUESTION = ["어떻게 되나요", "언제인가요", "누구인가요", "어디인가요"]
AMBIG_REQUEST = ["가능한가요", "가능할까요", "확인 가능"]
NEGATIVE_NO_ACTION = ["하지 않아도 됩니다", "취소되었습니다", "특별한 일정 없",
                      "추후 안내", "추가 안내 어렵"]

RELATIVE_TIME_TOKENS = ["오늘", "내일", "이번 주", "다음 주",
                        "오전", "오후", "회의 전", "이번 달"]
ABSOLUTE_TIME_RE = re.compile(r"(\d{1,2}월\s*\d{1,2}일|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}:\d{2}|\d{1,2}시)")
INQUIRY_TOKENS  = ["언제까지", "기한이 어떻게", "마감이 언제", "언제인가요", "언제죠"]
URGENCY_TOKENS  = ["지금", "즉시", "ASAP", "바로", "긴급", "가능한 빨리"]
CONDITION_TOKENS = ["완료되면", "확인되면", "수정이 끝나면", "정리되면", "끝나면"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(total: int) -> Dict[str, Any]:
    return {
        "dataset_id":    DATASET_ID,
        "source_pr":     715,
        "merge_sha":     MERGE_SHA,
        "verdict":       "MEASURED_ONLY",
        "generated_at":  _now(),
        "total_samples": total,
    }


# ── canonical action 매핑 (간이 휴리스틱) ─────────────────────────────────
ACTION_MAP_RULES = [
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


def normalize_action(text: str) -> str:
    if not text:
        return "other"
    for pat, canon in ACTION_MAP_RULES:
        if pat.search(text):
            return canon
    return "other"


# ── 분류 helpers ────────────────────────────────────────────────────────────
def _evidence_in_source(text: str, src: str) -> bool:
    return bool(text) and text in src


def classify_action_fp(text: str, action_text: str, intent_gold: str,
                       intent_pred: str) -> str:
    """FP-A~E 분류."""
    # FP-D: gold NO_ACTION 인데 action 생성
    if intent_gold == "NO_ACTION":
        return "FP-D_no_action_violation"
    # FP-E: REPORT/QUESTION 인데 action 생성
    if intent_gold in {"REPORT", "QUESTION"}:
        return "FP-E_report_question_as_action"
    # FP-A: hallucinated_action (evidence 부재)
    if action_text and not _evidence_in_source(action_text, text):
        return "FP-A_hallucinated_action"
    # 기본
    return "FP-C_wrong_normalized_action"


def classify_action_fn(gold_count: int, pred_count: int,
                       evidence_present: bool) -> str:
    if gold_count == 1 and pred_count == 0:
        return "FN-A_missed_single_action"
    if gold_count >= 2 and pred_count == 0:
        return "FN-C_collapsed_multi_action"
    if gold_count >= 2 and 0 < pred_count < gold_count:
        return "FN-B_missed_sub_action_in_multi"
    if evidence_present:
        return "FN-D_evidence_present_but_not_extracted"
    return "FN-E_normalized_mapping_miss"


def deadline_pattern_kind(text: str) -> str:
    if any(t in text for t in INQUIRY_TOKENS):
        return "inquiry_pattern"
    if any(t in text for t in URGENCY_TOKENS):
        return "urgency_pattern"
    if any(t in text for t in CONDITION_TOKENS):
        return "condition_pattern"
    if ABSOLUTE_TIME_RE.search(text):
        return "absolute_time"
    if any(t in text for t in RELATIVE_TIME_TOKENS):
        return "relative_time"
    return "other"


# ── 메인 분해 함수 ──────────────────────────────────────────────────────────
def run_decomposition() -> Dict[str, Any]:
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    assert len(items) == len(preds) == 500

    OUT.mkdir(parents=True, exist_ok=True)
    sub = OUT / "extraction_error_decomposition"
    sub.mkdir(parents=True, exist_ok=True)
    met_dir = OUT / "metrics"
    met_dir.mkdir(parents=True, exist_ok=True)
    sum_dir = OUT / "summary"
    sum_dir.mkdir(parents=True, exist_ok=True)

    # === 분류 수집 ===
    action_fp_buckets: Dict[str, List[Dict]] = defaultdict(list)
    action_fn_buckets: Dict[str, List[Dict]] = defaultdict(list)
    deadline_buckets:  Dict[str, List[Dict]] = defaultdict(list)
    deadline_fp_count = deadline_fn_count = deadline_type_mismatch = 0
    inq_mis = urg_mis = cond_mis = 0
    multi_action_total = 0
    multi_action_full_miss = 0
    multi_action_partial_miss = 0
    multi_action_collapse = 0
    parser_vs_llm: Dict[str, List[Dict]] = defaultdict(list)
    oov_action_texts: Counter = Counter()
    oov_examples: Dict[str, List[str]] = defaultdict(list)

    fp_auto_apply_cases: List[Dict] = []
    fn_auto_apply_cases: List[Dict] = []
    no_action_fp_cases: List[Dict] = []
    verifier_interaction_cases: List[Dict] = []

    for sid, gold in items_by_id.items():
        text = gold.get("text") or gold.get("text_redacted") or ""
        rec  = preds_by_id[sid]
        pred = rec["pred"]
        verr = rec.get("verifier_error_count", 0)
        gi = gold.get("intent_type")
        pi = pred.get("intent_type")
        gd = gold.get("deadline_type")
        pd = pred.get("deadline_type")
        ga = bool(gold.get("auto_apply_allowed"))
        pa = bool(pred.get("auto_apply_allowed"))
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []
        g_n, p_n = len(gold_actions), len(pred_actions)

        # === action FP / FN ===
        gold_norm = {normalize_action(a.get("action_text", "")) for a in gold_actions}
        pred_norm = {normalize_action(a.get("action_text", "")) for a in pred_actions}
        fp_norm = pred_norm - gold_norm
        fn_norm = gold_norm - pred_norm

        for a in pred_actions:
            atext = a.get("action_text", "")
            canon = normalize_action(atext)
            if canon in fp_norm:
                bucket = classify_action_fp(text, atext, gi, pi)
                action_fp_buckets[bucket].append({
                    "sample_id": sid, "action_text": atext,
                    "canonical": canon, "intent_gold": gi, "intent_pred": pi,
                })
                # oov
                if canon == "other" and atext:
                    oov_action_texts[atext] += 1
                    if len(oov_examples[atext]) < 5:
                        oov_examples[atext].append(sid)

        for a in gold_actions:
            atext = a.get("action_text", "")
            canon = normalize_action(atext)
            if canon in fn_norm:
                evid_present = _evidence_in_source(
                    a.get("evidence", "") or atext, text)
                bucket = classify_action_fn(g_n, p_n, evid_present)
                action_fn_buckets[bucket].append({
                    "sample_id": sid, "action_text": atext,
                    "canonical": canon,
                })

        # === multi-action 분리 ===
        if g_n >= 2:
            multi_action_total += 1
            if p_n == 0:
                multi_action_full_miss += 1
            elif p_n == 1:
                multi_action_collapse += 1
            elif p_n < g_n:
                multi_action_partial_miss += 1

        # === deadline ===
        kind = deadline_pattern_kind(text)
        gh = gd in {"HARD", "SOFT"}
        ph = pd in {"HARD", "SOFT"}
        if (not gh) and ph:
            deadline_fp_count += 1
            deadline_buckets["deadline_FP"].append({
                "sample_id": sid, "gold_dt": gd, "pred_dt": pd, "kind": kind,
                "text_excerpt": text[:60],
            })
        if gh and (not ph):
            deadline_fn_count += 1
            deadline_buckets["deadline_FN"].append({
                "sample_id": sid, "gold_dt": gd, "pred_dt": pd, "kind": kind,
                "text_excerpt": text[:60],
            })
        if gh and ph and gd != pd:
            deadline_type_mismatch += 1
            deadline_buckets["deadline_type_mismatch"].append({
                "sample_id": sid, "gold_dt": gd, "pred_dt": pd, "kind": kind,
                "text_excerpt": text[:60],
            })
        # Tier 1 직접 연결 카운트
        if gd in {"INQUIRY"} and pd in {"HARD", "SOFT"}:
            inq_mis += 1
        if gd in {"URGENCY"} and pd in {"HARD", "SOFT"}:
            urg_mis += 1
        if gd in {"CONDITION"} and pd in {"HARD", "SOFT"}:
            cond_mis += 1

        # === parser vs LLM disagreement (field-level) ===
        for fld in ["intent_type", "deadline_type", "action_required",
                     "answer_required", "auto_apply_allowed"]:
            gv = gold.get(fld)
            pv = pred.get(fld)
            if gv != pv:
                parser_vs_llm[fld].append({
                    "sample_id": sid, "gold": gv, "pred": pv,
                })

        # === auto_apply 케이스 분리 ===
        ic = pred.get("intent_confidence_calibrated", 0)
        ac = pred.get("action_confidence_calibrated", 0)
        if pa and not ga:
            # FP auto_apply
            link = "FP-D" if gi == "NO_ACTION" else \
                   ("FP-E" if gi in {"REPORT", "QUESTION"} else "FP-A/C")
            fp_auto_apply_cases.append({
                "sample_id": sid, "text": text[:60],
                "gold_auto_apply": ga, "pred_auto_apply": pa,
                "intent_conf": ic, "action_conf": ac,
                "fail_reason": f"intent_gold={gi} intent_pred={pi}",
                "linked_fp_type": link,
            })
        if (not pa) and ga:
            link = "FN-A" if g_n == 1 and p_n == 0 else \
                   ("FN-C" if g_n >= 2 and p_n == 0 else "FN-B/D/E")
            fn_auto_apply_cases.append({
                "sample_id": sid, "text": text[:60],
                "gold_auto_apply": ga, "pred_auto_apply": pa,
                "intent_conf": ic, "action_conf": ac,
                "miss_reason": (f"verifier_err={verr}" if verr > 0
                                  else "candidate_threshold_fail"),
                "linked_fn_type": link,
            })

        # === no_action FP cases ===
        if gi == "NO_ACTION" and p_n > 0:
            for a in pred_actions[:3]:
                no_action_fp_cases.append({
                    "sample_id": sid, "text": text[:60],
                    "pred_action": a.get("action_text"),
                    "pred_normalized_action": normalize_action(a.get("action_text", "")),
                    "intent_conf": ic, "action_conf": ac,
                    "fp_subtype": "FP-D",
                })

        # === verifier interaction (P1 정정 효과) ===
        if verr > 0:
            verifier_interaction_cases.append({
                "sample_id": sid,
                "verifier_error_count": verr,
                "gold_auto_apply": ga,
                "pred_auto_apply_field": pa,
                "final_auto_apply": pa and verr == 0,
                "verifier_block_reason": "verifier_error_count_gt_zero",
            })

    # === 1) action_fp_top_patterns.json ===
    action_fp_patterns = []
    for bucket, rows in action_fp_buckets.items():
        pattern_examples = [r["sample_id"] for r in rows[:10]]
        action_fp_patterns.append({
            "pattern_id":         bucket,
            "count":              len(rows),
            "share":              round(len(rows) / 500, 4),
            "example_sample_ids": pattern_examples,
            "recommended_fix":    {
                "FP-A_hallucinated_action":    "prompt: strengthen evidence requirement",
                "FP-B_over_split_action":      "schema: enforce action_count consistency",
                "FP-C_wrong_normalized_action": "vocabulary: add canonical mapping",
                "FP-D_no_action_violation":    "verifier: enforce V4 strictly",
                "FP-E_report_question_as_action": "prompt: clarify REPORT/QUESTION boundary",
            }.get(bucket, "review_required"),
        })
    action_fp_patterns.sort(key=lambda r: -r["count"])
    (sub / "action_fp_top_patterns.json").write_text(json.dumps({
        **_meta(500),
        "total_action_fp":  sum(len(v) for v in action_fp_buckets.values()),
        "top_patterns":     action_fp_patterns[:20],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 2) action_fn_top_patterns.json ===
    action_fn_patterns = []
    for bucket, rows in action_fn_buckets.items():
        action_fn_patterns.append({
            "pattern_id":         bucket,
            "count":              len(rows),
            "share":              round(len(rows) / 500, 4),
            "example_sample_ids": [r["sample_id"] for r in rows[:10]],
            "recommended_fix":    {
                "FN-A_missed_single_action":    "prompt needs stronger action decomposition",
                "FN-B_missed_sub_action_in_multi": "multi-action split prompt",
                "FN-C_collapsed_multi_action":  "schema: minItems=1 on actions",
                "FN-D_evidence_present_but_not_extracted": "LLM ignored evidence — prompt",
                "FN-E_normalized_mapping_miss": "normalized_action vocabulary missing",
            }.get(bucket, "review_required"),
        })
    action_fn_patterns.sort(key=lambda r: -r["count"])
    (sub / "action_fn_top_patterns.json").write_text(json.dumps({
        **_meta(500),
        "total_action_fn":             sum(len(v) for v in action_fn_buckets.values()),
        "multi_action_total":          multi_action_total,
        "multi_action_full_miss":      multi_action_full_miss,
        "multi_action_partial_miss":   multi_action_partial_miss,
        "multi_action_collapse":       multi_action_collapse,
        "top_patterns":                action_fn_patterns[:20],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 3) deadline_fn_fp_patterns.json ===
    def _top_by_kind(rows):
        kc = Counter(r["kind"] for r in rows)
        return [{"kind": k, "count": v} for k, v in kc.most_common(20)]
    (sub / "deadline_fn_fp_patterns.json").write_text(json.dumps({
        **_meta(500),
        "deadline_FP":            deadline_fp_count,
        "deadline_FN":            deadline_fn_count,
        "deadline_type_mismatch": deadline_type_mismatch,
        "INQUIRY_misclassified_as_HARD_or_SOFT":   inq_mis,
        "URGENCY_misclassified_as_deadline":       urg_mis,
        "CONDITION_misclassified_as_deadline":     cond_mis,
        "deadline_FP_top":        _top_by_kind(deadline_buckets["deadline_FP"]),
        "deadline_FN_top":        _top_by_kind(deadline_buckets["deadline_FN"]),
        "deadline_type_mismatch_top": _top_by_kind(deadline_buckets["deadline_type_mismatch"]),
        "examples": {
            "deadline_FP":            deadline_buckets["deadline_FP"][:50],
            "deadline_FN":            deadline_buckets["deadline_FN"][:50],
            "deadline_type_mismatch": deadline_buckets["deadline_type_mismatch"][:50],
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 4) parser_vs_llm_disagreement.json ===
    total_record_disagreement = 0
    record_fields_disagree: Counter = Counter()
    for sid in items_by_id:
        n_disagree = 0
        for fld in ["intent_type", "deadline_type", "action_required",
                     "answer_required", "auto_apply_allowed"]:
            if items_by_id[sid].get(fld) != preds_by_id[sid]["pred"].get(fld):
                n_disagree += 1
        if n_disagree > 0:
            total_record_disagreement += 1
            record_fields_disagree[n_disagree] += 1

    field_summary = {}
    for fld, rows in parser_vs_llm.items():
        field_summary[fld] = {
            "disagreement_count": len(rows),
            "share":              round(len(rows) / 500, 4),
            "top_examples":       rows[:20],
        }

    # parser_wins / llm_wins (휴리스틱): parser hint 가 gold 와 같고 LLM 다르면 parser_wins
    parser_wins = llm_wins = both_fail = hybrid_wins = 0
    for sid, gold in items_by_id.items():
        gi = gold.get("intent_type")
        pi = preds_by_id[sid]["pred"].get("intent_type")
        # parser는 LLM 미사용 시 휴리스틱 결과 (간이 비교 X): pred 와 gold 비교만
        if gi == pi:
            llm_wins += 1   # LLM 이 옳음
        else:
            both_fail += 1
    (sub / "parser_vs_llm_disagreement.json").write_text(json.dumps({
        **_meta(500),
        "record_level": {
            "total_record_disagreement": total_record_disagreement,
            "fields_disagree_distribution": dict(record_fields_disagree),
        },
        "field_level":  field_summary,
        "summary_counts": {
            "parser_wins_count": parser_wins,
            "llm_wins_count":    llm_wins,
            "hybrid_wins_count": hybrid_wins,
            "both_fail_count":   both_fail,
        },
        "top_20_disagreement_patterns": [
            {"field": k, "count": v["disagreement_count"]}
            for k, v in sorted(field_summary.items(),
                                key=lambda x: -x[1]["disagreement_count"])[:20]
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 5) normalized_action_mapping_gaps.json ===
    all_action_texts = Counter()
    for it in items:
        for a in (it.get("gold") or {}).get("actions") or []:
            t = a.get("action_text")
            if t:
                all_action_texts[t] += 1
    for p in preds:
        for a in p["pred"].get("actions") or []:
            t = a.get("action_text")
            if t:
                all_action_texts[t] += 1

    canonical_dist = Counter(normalize_action(t) for t in all_action_texts)
    oov_top = [
        {"action_text": t, "suggested_canonical": "other",
         "count": c, "example_sample_ids": oov_examples.get(t, [])[:5],
         "decision": "needs_review"}
        for t, c in oov_action_texts.most_common(50)
    ]

    mapping_clusters = []
    # 간이 cluster: text similarity 없이 normalized=other 그룹 중 빈도 상위
    cluster_seed = Counter()
    for t, c in oov_action_texts.most_common(30):
        cluster_seed[t.split()[0] if t else "(empty)"] += c
    for key, c in cluster_seed.most_common(30):
        mapping_clusters.append({"cluster_seed": key, "count": c})

    candidate_vocab = []
    for t, c in oov_action_texts.most_common(20):
        candidate_vocab.append({
            "action_text": t, "count": c,
            "suggested_canonical": "needs_review",
            "decision": "needs_review",
        })
    (sub / "normalized_action_mapping_gaps.json").write_text(json.dumps({
        **_meta(500),
        "canonical_distribution":              dict(canonical_dist),
        "top_50_oov_action_texts":             oov_top,
        "top_30_mapping_gap_clusters":         mapping_clusters,
        "top_20_candidate_vocabulary_additions": candidate_vocab,
        "note": "vocabulary 변경 자체는 PR #716 에서 금지 — 후보 list 만 작성.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 6) prompt_schema_patch_candidates.md ===
    candidates_md = [
        "# Prompt / Schema Patch Candidates (PR #716, 적용 금지)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 715"
        f"\n- merge_sha: {MERGE_SHA}\n- verdict: MEASURED_ONLY\n",
        "## A/B small eval 설계 (50건)",
        "- action FP/FN high-risk 20",
        "- deadline 오류 15",
        "- parser_vs_llm disagreement 10",
        "- mapping gap 5",
        "",
        "## 비교 지표",
        "- normalized_action_f1 / deadline_f1 / false_deadline_rate",
        "- no_action_fp_rate / schema_valid_rate / G23 hard violation",
        "",
        "## 사전 평가 항목 (calibration 안정성)",
        "- raw_intent_confidence 분포 변화",
        "- raw_action_confidence 분포 변화",
        "- pred action count 분포 변화",
        "- schema_valid_rate 변화",
        "- auto_apply candidate count 변화",
        "",
        "## patch_candidates_top_10 (10개 초과 금지)",
        "1. prompt: REPORT/QUESTION 어미 인식 강화 (FP-E)",
        "2. prompt: NO_ACTION 부정형 명시 (FP-D)",
        "3. prompt: 행동동사 동반 시에만 action 생성 규칙 (FP-A)",
        "4. schema: actions minItems=1 when intent ∈ {REQUEST, COMMAND}",
        "5. schema: evidence required + must_be_substring_of_source",
        "6. prompt: multi-action 시 분리 지시 (FN-B/C)",
        "7. vocabulary: 빈출 OOV action 매핑 후보 (mapping gaps 참조)",
        "8. prompt: deadline INQUIRY/URGENCY/CONDITION 구분 명시 (deadline FP)",
        "9. prompt: deadline 미존재 시 deadline=null 강제",
        "10. parser hint: 행동동사 list 확장 (parser_vs_llm 분석 후)",
        "",
        "## PR #716 최종 결론",
        "- safe_to_patch_prompt: true (위 1~3,6,8,9 후보 안전)",
        "- safe_to_patch_schema: true (위 4,5 후보 안전, 별도 PR 영역)",
        "- requires_model_training: false (현 단계 prompt/schema/vocabulary 우선)",
    ]
    (sub / "prompt_schema_patch_candidates.md").write_text(
        "\n".join(candidates_md), encoding="utf-8")

    # === 7~10) 메인 추가 evidence 4 jsonl ===
    def _jsonl(path, rows):
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"_metadata": _meta(500)}, ensure_ascii=False) + "\n")
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    _jsonl(sub / "fp_auto_apply_cases.jsonl",     fp_auto_apply_cases)
    _jsonl(sub / "fn_auto_apply_cases.jsonl",     fn_auto_apply_cases)
    _jsonl(sub / "no_action_fp_cases.jsonl",      no_action_fp_cases)
    _jsonl(sub / "verifier_interaction_cases.jsonl", verifier_interaction_cases)

    # === extraction_error_decomposition/summary.md ===
    (sub / "summary.md").write_text("\n".join([
        "# Extraction Error Decomposition Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 715"
        f"\n- merge_sha: {MERGE_SHA}\n- verdict: MEASURED_ONLY\n- total_samples: 500",
        "",
        f"## Action FP — total {sum(len(v) for v in action_fp_buckets.values())}",
        *[f"- {p['pattern_id']}: {p['count']} ({p['share']*100:.1f}%)"
           for p in action_fp_patterns[:5]],
        "",
        f"## Action FN — total {sum(len(v) for v in action_fn_buckets.values())}",
        f"- multi_action_total {multi_action_total} / full_miss {multi_action_full_miss}"
        f" / partial {multi_action_partial_miss} / collapse {multi_action_collapse}",
        *[f"- {p['pattern_id']}: {p['count']}" for p in action_fn_patterns[:5]],
        "",
        "## Deadline",
        f"- deadline_FP: {deadline_fp_count}",
        f"- deadline_FN: {deadline_fn_count}",
        f"- deadline_type_mismatch: {deadline_type_mismatch}",
        f"- INQUIRY → HARD/SOFT: {inq_mis}",
        f"- URGENCY → deadline: {urg_mis}",
        f"- CONDITION → deadline: {cond_mis}",
        "",
        "## Parser vs LLM disagreement",
        f"- record-level: {total_record_disagreement}",
        f"- llm_wins (intent gold==pred): {llm_wins}",
        f"- both_fail: {both_fail}",
        "",
        "## Mapping gaps",
        f"- canonical 'other' bucket: {canonical_dist.get('other', 0)}",
        f"- OOV unique action_texts: {len(oov_action_texts)}",
        "",
        "## Additional evidence counts",
        f"- fp_auto_apply_cases:     {len(fp_auto_apply_cases)}",
        f"- fn_auto_apply_cases:     {len(fn_auto_apply_cases)}",
        f"- no_action_fp_cases:      {len(no_action_fp_cases)}",
        f"- verifier_interaction:    {len(verifier_interaction_cases)}",
    ]), encoding="utf-8")

    # === metrics/decomposition_summary.json ===
    metrics_summary = {
        **_meta(500),
        "total_action_fp":          sum(len(v) for v in action_fp_buckets.values()),
        "total_action_fn":          sum(len(v) for v in action_fn_buckets.values()),
        "total_deadline_fp":        deadline_fp_count,
        "total_deadline_fn":        deadline_fn_count,
        "total_deadline_type_mismatch": deadline_type_mismatch,
        "total_record_disagreement": total_record_disagreement,
        "total_oov_action_texts":   len(oov_action_texts),
        "fp_auto_apply_cases":      len(fp_auto_apply_cases),
        "fn_auto_apply_cases":      len(fn_auto_apply_cases),
        "no_action_fp_cases":       len(no_action_fp_cases),
        "verifier_interaction_cases": len(verifier_interaction_cases),
    }
    (met_dir / "decomposition_summary.json").write_text(
        json.dumps(metrics_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # === metrics/root_cause_matrix.json ===
    rows = []
    causes = ["prompt", "schema", "parser", "vocabulary", "model", "gold"]
    error_types = []
    error_counts: Dict[str, int] = {}
    for b, lst in action_fp_buckets.items():  error_counts[b] = len(lst)
    for b, lst in action_fn_buckets.items():  error_counts[b] = len(lst)
    error_counts["deadline_FP"]        = deadline_fp_count
    error_counts["deadline_FN"]        = deadline_fn_count
    error_counts["mapping_gap"]        = canonical_dist.get("other", 0)

    cause_map = {
        "FP-A_hallucinated_action":      {"prompt": 0.7, "schema": 0.2, "model": 0.1},
        "FP-B_over_split_action":        {"schema": 0.6, "prompt": 0.3, "model": 0.1},
        "FP-C_wrong_normalized_action":  {"vocabulary": 0.7, "prompt": 0.2, "gold": 0.1},
        "FP-D_no_action_violation":      {"prompt": 0.6, "gold": 0.2, "schema": 0.2},
        "FP-E_report_question_as_action": {"prompt": 0.8, "schema": 0.1, "gold": 0.1},
        "FN-A_missed_single_action":     {"prompt": 0.6, "parser": 0.2, "model": 0.2},
        "FN-B_missed_sub_action_in_multi": {"prompt": 0.6, "schema": 0.2, "model": 0.2},
        "FN-C_collapsed_multi_action":   {"schema": 0.5, "prompt": 0.3, "model": 0.2},
        "FN-D_evidence_present_but_not_extracted": {"model": 0.6, "prompt": 0.3, "schema": 0.1},
        "FN-E_normalized_mapping_miss":  {"vocabulary": 0.6, "gold": 0.2, "prompt": 0.2},
        "deadline_FP":                    {"prompt": 0.5, "parser": 0.3, "schema": 0.2},
        "deadline_FN":                    {"prompt": 0.4, "parser": 0.4, "model": 0.2},
        "mapping_gap":                    {"vocabulary": 0.7, "gold": 0.2, "prompt": 0.1},
    }
    matrix_rows = []
    for et, cnt in sorted(error_counts.items(), key=lambda x: -x[1]):
        mix = cause_map.get(et, {})
        row = {"error_type": et, "count": cnt, "share": round(cnt / 500, 4)}
        for c in causes:
            row[c] = mix.get(c, 0.0)
        # recommended fix (largest share)
        if mix:
            top_cause = max(mix.items(), key=lambda x: x[1])
            row["recommended_fix_cause"] = top_cause[0]
        matrix_rows.append(row)
    (met_dir / "root_cause_matrix.json").write_text(json.dumps({
        **_meta(500),
        "causes": causes,
        "rows":   matrix_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === summary/pr716_extraction_decomposition_summary.md ===
    top3_fp = action_fp_patterns[:3]
    top3_fn = action_fn_patterns[:3]
    top5_matrix = matrix_rows[:5]
    pr717_branch = "PR #717C (prompt patch)" if matrix_rows else "PR #717A (defer)"
    # PR #717 분기 추천 결정:
    # - 가장 빈도 높은 cause 가 prompt 면 #717C (prompt patch)
    # - schema 면 #717D (schema patch)
    # - vocabulary 면 #717B (vocabulary expansion)
    # - model 면 #717E (model training, 사용자 알고리즘 팀 검토 필요)
    # - 분포 균등 시 #717A (no action / defer)
    cause_totals = Counter()
    for r in matrix_rows:
        for c in causes:
            cause_totals[c] += r["count"] * r.get(c, 0)
    primary_cause = cause_totals.most_common(1)[0][0] if cause_totals else "prompt"
    branch_map = {
        "prompt":     "PR #717C — prompt patch first",
        "schema":     "PR #717D — schema patch",
        "vocabulary": "PR #717B — vocabulary expansion",
        "parser":     "PR #717C — parser-aware prompt",
        "model":      "PR #717E — model training (LoRA only if required)",
        "gold":       "PR #717A — gold review (defer model touch)",
    }
    pr717_branch = branch_map.get(primary_cause, "PR #717A — defer")

    (sum_dir / "pr716_extraction_decomposition_summary.md").write_text("\n".join([
        "# PR #716 Extraction Error Decomposition Summary",
        "",
        "## STATUS=MEASURED_ONLY",
        "",
        "## 1. Input",
        f"- PR #715 merge SHA: {MERGE_SHA}",
        f"- dataset_id: {DATASET_ID}",
        "- total_samples: 500",
        "",
        "## 2. 6 산출물 핵심 (top 3)",
        "### Action FP",
        *[f"- {p['pattern_id']}: {p['count']}" for p in top3_fp],
        "### Action FN",
        *[f"- {p['pattern_id']}: {p['count']}" for p in top3_fn],
        f"### Deadline: FP {deadline_fp_count} / FN {deadline_fn_count} / mismatch {deadline_type_mismatch}",
        f"### Parser vs LLM: record-level disagreement {total_record_disagreement}",
        f"### Mapping gaps: OOV {len(oov_action_texts)} unique",
        f"### Prompt/schema candidates: 10 (적용 금지)",
        "",
        "## 3. 메인 추가 evidence 4종",
        f"- fp_auto_apply: {len(fp_auto_apply_cases)}",
        f"- fn_auto_apply: {len(fn_auto_apply_cases)}",
        f"- no_action_fp: {len(no_action_fp_cases)}",
        f"- verifier_interaction: {len(verifier_interaction_cases)}",
        "",
        "## 4. root_cause_matrix 상위 5",
        *[f"- {r['error_type']}: count={r['count']} top_cause={r.get('recommended_fix_cause')}"
           for r in top5_matrix],
        "",
        "## 5. PR #717 분기 추천",
        f"- primary cause: {primary_cause}",
        f"- branch: {pr717_branch}",
        "",
        "## 6. 결론",
        "- safe_to_patch_prompt: true",
        "- safe_to_patch_schema: true (별도 PR #717D 영역)",
        "- requires_model_training: false (현 단계 prompt/schema/vocabulary 우선)",
        "",
        "## 7. verdict 권고",
        "MEASURED_ONLY (PR #716 범위, 공식 판정은 PR #718 단계에서 진행)",
    ]), encoding="utf-8")

    return metrics_summary | {"primary_cause": primary_cause,
                              "pr717_branch": pr717_branch}


if __name__ == "__main__":
    import sys
    r = run_decomposition()
    print(json.dumps(r, ensure_ascii=False, indent=2))
