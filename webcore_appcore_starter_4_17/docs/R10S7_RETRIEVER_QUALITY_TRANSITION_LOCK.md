# R10-S7 Transition Lock: Retriever Quality (Always On Invariants)

## 1) Status
- R10-S7 Build Anchor Incident: **CLOSED & SEALED**
- Next Mission: **S7 Retriever Quality (Recall/Precision improvement with regression gates)**

## 2) Always On (Invariant Rules) — No Exceptions
### Always On-1: Build Anchor Gate
- verify + destructive + proof/.latest는 PR/로컬/CI 어디서든 상시 가동
- CI에서 optional/skip이 되는 순간 즉시 Block

### Always On-2: Meta-only Policy
- 텔레메트리/로그에 원문(Text) 유출 0
- 실험/편의 목적의 우회 금지 (Always On)

## 3) S7 Quality Definition (Metrics)
Retriever 품질은 랭킹/검색 품질 지표로 평가한다.
- Precision@K / Recall@K
- MRR@K
- nDCG@K (graded relevance가 있을 때)

> 목적: Recall을 끌어올리되, Precision 붕괴를 막고, "첫 relevant"가 상위에 오도록(MRR), 상위 랭킹 품질(nDCG)을 개선한다.

## 4) Regression Gate (Phase Plan)
- Phase 0: 평가 파이프라인/Golden Set 스키마 고정(결정적 실행, 메타-only 로그)
- Phase 1: 기준선(Baseline) 확정 + PR마다 결과 기록(artifact/로그)
- Phase 2: Baseline 대비 하락 차단(merge 불가) + 개선 PR만 통과

## 5) Developer Quick Check (Always On)
S7 작업 시작 전 아래 ops 스크립트로 Always On 상태를 자가 점검한다.
- scripts/ops/verify_s7_always_on.sh
