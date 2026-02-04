# Master SEALED Index (P0 + P1) — 2026-01-31

Status: PASS (SEALED)

이 문서는 P0/P1 완료 정본을 한 곳에서 찾을 수 있게 만드는 "단일 진입점"입니다.
팀이 늘어나도 기준선이 흔들리지 않도록, 검증 앵커 1줄과 SEALED 문서 링크만 고정합니다.

## Verification anchor (main)

```bash
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"
```

Expected:

EXIT=0

## SEALED records

### P0 (P0-1..P0-6)

Doc: docs/ops/SEALED_RECORDS/2026-01-31_P0_P6_SEALED.md

PR: #281 (merged)

### P1 (Supplychain / Update / Store)

Doc: docs/ops/SEALED_RECORDS/2026-01-31_P1_SUPPLYCHAIN_UPDATE_STORE_SEALED.md

PR: #282 (merged)

### M6 (Ops Hub Traceability)

M6는 기준선 키로 편입됨 (OPS_HUB_TRACEABILITY_*_OK=1).

Doc: docs/ops/SEALED_RECORDS/2026-02-01_M6_SEALED.md

PR: #284, #285, #286, #287, #289, #290, #291, #292 (merged), #288 (merged=false, #291에서 재적용)

## What this baseline guarantees (non-reversible)

- reason_code single source + drift guard
- model pack apply fail-closed E2E (verify failure => apply=0 + state unchanged)
- model pack identity + expiry required (fail-closed)
- export approve auditv2 no-miss + idempotent
- P95 marks parity (UI↔request_id↔runtime headers joinability)
- meta-only negative suite leak tests (fail-closed)
- supplychain DSSE attestation verify + actor identity
- update anti-rollback persisted + atomic bump
- real DB adapter parity (sql.js)

## Team share message (copy/paste)

Baseline SEALED (P0+P1) is fixed on main.
- Verify: `bash scripts/verify/verify_repo_contracts.sh ; echo EXIT=$?`  (expect EXIT=0)
- Master index: docs/ops/SEALED_RECORDS/2026-01-31_P0_P1_MASTER_INDEX.md
- P0 SEALED: docs/ops/SEALED_RECORDS/2026-01-31_P0_P6_SEALED.md
- P1 SEALED: docs/ops/SEALED_RECORDS/2026-01-31_P1_SUPPLYCHAIN_UPDATE_STORE_SEALED.md


## M7 SEALED
- docs/ops/SEALED_RECORDS/2026-02-01_M7_SEALED.md

## M8 SEALED
- docs/ops/SEALED_RECORDS/2026-02-02_M8_SEALED.md
