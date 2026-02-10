# P1-PLAT-01 DoD Keys v1 (SSOT)

## 목적
PR-1이 "완료됐다"를 판정할 키를 추가로 고정합니다.

## PR-1 필수 DoD 키 (추가만)

### 필수
- `OPS_HUB_TRACE_DB_SCHEMA_OK=1`
- `OPS_HUB_TRACE_REQUEST_ID_INDEX_OK=1`
- `OPS_HUB_TRACE_IDEMPOTENT_UPSERT_OK=1`
- `OPS_HUB_TRACE_CONCURRENCY_SAFE_OK=1`
- `OPS_HUB_TRACE_LOCAL_ONLY_OR_AUTH_OK=1` (기존 불변, 유지)

### 권장
- `OPS_HUB_TRACE_EVENT_SCHEMA_V1_OK=1`

## 통합 위치
`scripts/verify/verify_repo_contracts.sh`에 "추가만" 형태로 반영
- 기존 키 변경/삭제 0

