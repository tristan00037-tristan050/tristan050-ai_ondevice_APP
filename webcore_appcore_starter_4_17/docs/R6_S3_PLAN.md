# R6-S3 Plan — Persistence & App Integration

## P0 — Persistence (PostgreSQL)

- Exports, Reconciliation 영구화 (USE_PG=1)
- 마이그레이션/DDL: packages/data-pg/migrations
- CI 서비스(Postgres) + `persistence-e2e` 락

## P1 — App-Core & HUD

- HUD: 승인/대사 요약 표시(Top-N alternatives 포함)
- App-Core 암호화(로컬 at-rest key 관리) 설계 반영

## Merge Gates (unchanged + persistence)

- 데이터 품질(≥50, ≤30%), 정확도(Top-1/Top-5), E2E(긍/부정), Roles/Idempotency
- **추가:** `persistence-e2e` (API→DB 적재 검증)


