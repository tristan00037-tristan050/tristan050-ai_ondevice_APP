# R6-S4 Release Checklist (Accounting)

## Build & Artifacts

- [ ] Tag: `r6-s4-YYYYMMDD`
- [ ] CI `release-bff` ✅ (build/migrate/container smoke)

## Data & Gates (must be green)

- [ ] ci:gold-size (≥50), ci:gold-synthetic (≤30%)
- [ ] ci:gate:accuracy (Top-1≥0.70, Top-5≥0.85)
- [ ] smoke:accounting:all + Approvals/Exports(+neg) + Reconciliation
- [ ] persistence-e2e (Postgres + migrate + API→DB)
- [ ] app-typecheck (App-Core encryption/HUD)

## Runtime

- [ ] EXPORT_SIGN_SECRET 로테이션 정책 적용
- [ ] `X-Request-Id` 로깅 및 수집 파이프 확인
- [ ] /health, /ready 헬스프로브 연결(LB/K8s)

## Rollback (Runbook)

- [ ] db: 백필/스냅샷 전략 문서 확인
- [ ] 태그 이전 이미지/마이그레이션 리비전 명시

## 운영 런타임 가이드

### 요청 추적
- 모든 요청은 X-Request-Id를 자동 발급/반영(클라이언트 제공 시 승계)
- 구조화 로그(JSON)에 id/tenant/idem/ms 포함 → APM/로그 파이프에 바로 적재

### 헬스/레디
- `/health` = 프로세스 생존 체크
- `/ready` = 트래픽 수신 준비. K8s/LB 프로브에 연결

### 시크릿
- EXPORT_SIGN_SECRET 주기적 로테이션(문서의 Release Checklist 참조)

### 롤백
- 태그 단위 이미지 + 마이그레이션 리비전으로 즉시 복구(Release 문서에 절차 고정)


