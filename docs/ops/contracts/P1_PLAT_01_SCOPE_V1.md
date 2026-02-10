# P1-PLAT-01 Scope v1 (SSOT)

## 목적
PR-1에 반드시 포함되어야 하는 파일 경로를 고정합니다.

## PR-1 필수 변경 경로 (정본)

### 1. Trace Store (sql.js)
```
packages/ops-hub/src/trace/store/db/sqljs_store.ts
```
- sql.js 기반 trace 이벤트 저장소
- idempotent upsert (UNIQUE 제약조건 사용)
- 동시성 안전 보장

### 2. Trace Event Schema
```
packages/ops-hub/src/trace/schema/trace_event_v1.ts
```
- trace_event_v1 스키마 정의
- request_id 인덱스 포함

### 3. Trace HTTP Routes
```
packages/ops-hub/src/trace/http/routes/v1_trace.ts
```
- POST /v1/trace 엔드포인트
- meta-only 검증 (저장 전)
- X-Api-Key 값 매칭
- 127.0.0.1 바인딩 또는 인증 필수

### 4. Verify Script
```
scripts/verify/verify_ops_hub_trace_db_store.sh
```
- schema smoke 테스트
- idempotent 테스트
- concurrency 테스트 (Promise.all)
- no-raw negative-first 테스트

### 5. Repo Contracts Integration
```
scripts/verify/verify_repo_contracts.sh
```
- DoD 키 추가만 (기존 키 변경/삭제 0)

## 변경 범위 고정

위 경로들을 포함하도록 작업 범위가 확정되어야 합니다.

