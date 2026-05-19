"""build_eval_set.py — D-4 Card 2 평가셋 생성 (redacted 합성).

페르소나 5종 × 10건 = 50건. tier 분포 S20/M20/L10. XL 차단 케이스 별도 5건.
raw paragraph 저장 0 — text_redacted / synthetic_slot_id / PII placeholder 만.
외부 API 호출 0 · 학습 아님 (평가 전용).
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "evaluation/card2/eval_set_v1.jsonl"

PERSONAS = ["startup_founder", "accountant", "hr_manager", "sales_lead", "ops_manager"]
# 페르소나별 슬롯 후보 (synthetic_slot_id)
SLOTS = {
    "startup_founder": ["market_tam", "funding_round", "team_size"],
    "accountant":      ["revenue", "net_profit", "tax_due"],
    "hr_manager":      ["headcount", "payroll_total", "hire_plan"],
    "sales_lead":      ["pipeline_value", "win_rate", "quota"],
    "ops_manager":     ["lead_time", "defect_rate", "throughput"],
}
# tier 순환: S,S,M,M,L,S,S,M,M,L → 10건당 S4 M4 L2 → 5페르소나 = S20 M20 L10
TIER_CYCLE = ["S", "S", "M", "M", "L", "S", "S", "M", "M", "L"]


def build_items() -> list[dict]:
    items: list[dict] = []
    for p in PERSONAS:
        slots = SLOTS[p]
        for i in range(10):
            tier = TIER_CYCLE[i]
            slot = slots[i % len(slots)]
            # 짝수 i: 출처 사실 + 인용 있음(채움 가능), 홀수 i: 출처 부재(blank 기대)
            has_source = (i % 2 == 0)
            items.append({
                "case_id": f"card2_eval_{p}_{i:02d}",
                "persona": p,
                "tier": tier,
                "synthetic_slot_id": slot,
                "text_redacted": f"[REDACTED persona={p} slot={slot} sample={i}]",
                "pii_placeholders": ["<PERSON>", "<ORG>", "<AMOUNT>"],
                "source_fact_present": has_source,
                "citation_present": has_source,
                "wiki_only": (not has_source and i in (3, 7)),
                "expected_decision": "fill_candidate" if has_source else "blank",
                "raw_text_retained": False,
            })
    return items


def build_xl_block_cases() -> list[dict]:
    """XL 차단 케이스 별도 5건 — 처리 거부 기대."""
    return [{
        "case_id": f"card2_eval_xl_block_{i:02d}",
        "persona": PERSONAS[i],
        "tier": "XL",
        "synthetic_slot_id": "n/a",
        "text_redacted": "[REDACTED oversized document]",
        "pii_placeholders": [],
        "source_fact_present": False,
        "citation_present": False,
        "wiki_only": False,
        "expected_decision": "blocked",
        "raw_text_retained": False,
    } for i in range(5)]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    items = build_items() + build_xl_block_cases()
    with OUT.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    s = sum(1 for it in items if it["tier"] == "S")
    m = sum(1 for it in items if it["tier"] == "M")
    el = sum(1 for it in items if it["tier"] == "L")
    xl = sum(1 for it in items if it["tier"] == "XL")
    print(json.dumps({"total": len(items), "S": s, "M": m, "L": el, "XL_block": xl,
                       "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
