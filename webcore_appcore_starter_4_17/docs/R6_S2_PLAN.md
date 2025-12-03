# R6‑S2 PLAN (Accounting)

## P1 — 데이터 품질

- 합성 ≤ 30%, 실제/수작업 ≥ 70% (CI: ci:gold-synthetic)
- GOLDENSET_QA_CHECKLIST 준수

## 기능 — Approvals / Exports / Reconciliation

- **Approvals**: POST /v1/accounting/approvals/:id (role=operator, Idempotency-Key 필수)
- **Exports**: POST /v1/accounting/exports/reports, GET /v1/accounting/exports/:jobId (role=auditor)
- **Reconciliation**: 어댑터 인터페이스 설계 → 다음 스프린트에 구현

## 머지 게이트

- 계약/스키마, 금지 규칙, 데이터 품질(합성/수량/PII), 정확도(Top‑1/Top‑5), E2E(BFF+Approvals/Exports)

## API 엔드포인트

### Approvals
- `POST /v1/accounting/approvals/:id` - 승인/반려
  - 역할: operator 이상
  - 필수 헤더: Idempotency-Key, X-Api-Key, X-Tenant
  - 요청 본문: `{ action: "approve" | "reject", client_request_id: string, note?: string }`

### Exports
- `POST /v1/accounting/exports/reports` - Export 잡 생성
  - 역할: auditor 이상
  - 필수 헤더: Idempotency-Key, X-Api-Key, X-Tenant
  - 요청 본문: `{ since?: string, until?: string, severity?: string[], limitDays?: number }`
  - 제한: limitDays ≤ 90일

- `GET /v1/accounting/exports/:jobId` - Export 잡 상태 조회
  - 역할: auditor 이상
  - 필수 헤더: X-Api-Key, X-Tenant

## E2E 테스트

- `npm run test:e2e:accounting:approvals` - Approvals E2E
- `npm run test:e2e:accounting:exports` - Exports E2E


