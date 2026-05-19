"""build_slot_lexicon.py — D-4 Card 2 슬롯 패턴 lexicon 생성.

슬롯 id → 라벨 매칭 후보 토큰. mapper.compute_slot_confidence 의 lexicon_hit
요소에 사용. 학습 아님 — 룰 보조 lexicon. 외부 API 호출 0.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = (Path(__file__).resolve().parents[3]
       / "butler_pc_core/cards/document_transform/slot_pattern_lexicon.json")

LEXICON = {
    "market_tam":     ["시장", "규모", "tam", "market", "size"],
    "funding_round":  ["투자", "라운드", "funding", "round", "시리즈"],
    "team_size":      ["팀", "인원", "team", "headcount", "규모"],
    "revenue":        ["매출", "수익", "revenue", "sales"],
    "net_profit":     ["순이익", "이익", "profit", "net"],
    "tax_due":        ["세금", "납부", "tax", "due"],
    "headcount":      ["인원", "headcount", "직원", "employees"],
    "payroll_total":  ["급여", "인건비", "payroll", "총액"],
    "hire_plan":      ["채용", "계획", "hire", "plan"],
    "pipeline_value": ["파이프라인", "pipeline", "value", "금액"],
    "win_rate":       ["수주", "win", "rate", "율"],
    "quota":          ["할당", "quota", "목표", "target"],
    "lead_time":      ["리드", "lead", "time", "기간"],
    "defect_rate":    ["불량", "defect", "rate", "율"],
    "throughput":     ["처리량", "throughput", "생산"],
}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_meta": {
            "version": "1.0",
            "purpose": "slot label matching lexicon (rule-assist, not training)",
            "is_training_artifact": False,
            "is_retrieval_or_eval_only": True,
        },
        "lexicon": LEXICON,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"slots": len(LEXICON), "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
