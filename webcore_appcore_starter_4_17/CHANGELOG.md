# Changelog

## R6-S4 (Release)

- BFF: 요청 ID + 구조화 액세스 로그
- /ready 엔드포인트 추가 (프로브용)
- Dockerfile/Compose/CI Release 파이프라인 추가
- 문서: Release Checklist/Runbook

## R6-S3.2

- HUD UI 화면 (Suggest/Approval/Export/Reconciliation)
- 오프라인 큐 (암호화 저장 + 자동 재시도)
- 스크린 프라이버시 (백그라운드 블러 + 스크린캡처 차단)
- Idempotency-Key 오버라이드 지원
- 온라인 상태 감지 훅

## R6-S3.1

- 로컬 암호화 스토리지 (AES-GCM, SecureStore + MMKV)
- 키 회전 기능 (모든 레코드 재암호화)
- HUD API 래퍼 (suggest/approvals/exports/recon)
- Idempotency-Key 자동 생성
- 타입 안정성 게이트 (typecheck:app)

## R6-S3

- PostgreSQL 데이터 계층 (data-pg 패키지)
- 마이그레이션 시스템 (001_init.sql)
- Exports/Reconciliation 영구화 (USE_PG=1)
- 멱등성 캐시 (DB UNIQUE INDEX)
- 퍼시스턴스 E2E 테스트 (API→DB 검증)
- CI Postgres 서비스 + persistence-e2e 단계


