# P1-PLAT-01 Verify Requirements v1 (SSOT)

## 목적
verify_ops_hub_trace_db_store.sh에 반드시 들어가야 하는 테스트를 고정합니다.

## 반드시 포함 (4개)

### 1. Schema Smoke
- **목적**: 정상 insert 1회 성공
- **검증**: trace_event_v1 스키마로 데이터 저장 성공

### 2. Idempotent
- **목적**: 동일 event_id 2회 ingest → 저장 1회
- **검증**: 
  - 동일 event_id로 2회 insert 시도
  - DB에 1건만 저장됨 (UNIQUE 제약조건 확인)
  - 코드 if가 아닌 DB 제약조건으로 보장

### 3. Concurrency
- **목적**: Promise.all 동시 ingest 2개
- **검증**:
  - 같은 request_id, 다른 event_id
  - Promise.all로 동시 실행
  - 둘 다 존재 + 깨진 JSON/partial write 0
  - 순차 실행이 아닌 진짜 동시성 검증

### 4. No-Raw Negative-First
- **목적**: 금지 키 payload → 저장 0 (FAIL-CLOSED)
- **검증**:
  - 금지 키(prompt, raw, text 등) 포함 payload
  - 저장 전에 차단 (저장 후 필터 금지)
  - 저장 0건 확인

## 검증 방법
- verify 스크립트는 빌드 없이 실행 가능해야 함
- dist require 의존 금지
- 판정만 수행

