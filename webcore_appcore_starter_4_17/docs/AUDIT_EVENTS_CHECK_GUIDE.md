# Audit 이벤트 확인 가이드

## 1. 수동 테스트 시나리오

다음 작업을 HUD에서 수행하세요:

1. **승인 테스트**
   - HUD에서 추천 결과를 보고 "승인" 버튼 클릭
   - `approval_apply` 이벤트가 생성되어야 함

2. **Manual Review 테스트**
   - HIGH_VALUE 케이스: 금액이 100만원 이상인 거래에서 "수동 검토 요청" 클릭
   - LOW_CONFIDENCE 케이스: 금액이 100만원 미만인 거래에서 "수동 검토 요청" 클릭
   - 각각 `manual_review_request` 이벤트가 생성되어야 함

3. **External Sync 테스트**
   - 외부 sync를 한 번 실행 (예: `node scripts/worker_sync_external.mjs`)
   - `external_sync_start`, `external_sync_success` (또는 `external_sync_error`) 이벤트가 생성되어야 함

---

## 2. psql 쿼리로 이벤트 확인

### DATABASE_URL 설정

```bash
# 로컬 개발 환경 (기본값)
export DATABASE_URL="postgres://app:app@localhost:5432/app"

# 또는 .env 파일에서 로드
source .env
```

### psql 접속 방법

```bash
# 방법 1: 환경변수 사용
psql $DATABASE_URL

# 방법 2: 직접 연결 문자열 지정
psql "postgres://app:app@localhost:5432/app"

# 방법 3: SQL 파일 실행
psql $DATABASE_URL -f scripts/check_audit_events.sql
```

### 핵심 확인 쿼리

#### 1) 승인 이벤트 샘플

```sql
SELECT 
  action, 
  subject_type, 
  subject_id,
  payload->>'top1_selected' AS top1_selected,
  payload->>'selected_rank' AS selected_rank,
  payload->>'ai_score' AS ai_score,
  payload->>'note' AS note,
  ts
FROM accounting_audit_events
WHERE action = 'approval_apply'
ORDER BY ts DESC
LIMIT 10;
```

**확인 포인트:**
- `top1_selected`: `true` 또는 `false` 값이 있어야 함
- `selected_rank`: `1`, `2`, `3` 등의 숫자 값이 있어야 함
- `ai_score`: `0.85` 같은 0~1 사이의 숫자 값이 있어야 함

#### 2) Manual Review 이벤트 샘플

```sql
SELECT 
  action, 
  subject_type, 
  subject_id,
  payload->>'reason_code' AS reason_code,
  payload->>'amount' AS amount,
  payload->>'currency' AS currency,
  payload->>'is_high_value' AS is_high_value,
  payload->>'reason' AS reason,
  ts
FROM accounting_audit_events
WHERE action = 'manual_review_request'
ORDER BY ts DESC
LIMIT 10;
```

**확인 포인트:**
- `reason_code`: `HIGH_VALUE` 또는 `LOW_CONFIDENCE` 값이 있어야 함
- `amount`: 숫자 값 (예: `1500000`)
- `currency`: `KRW` 같은 통화 코드
- `is_high_value`: `true` 또는 `false` 값

#### 3) External Sync 이벤트 샘플

```sql
SELECT 
  action,
  subject_id AS source,
  payload->>'source' AS source_from_payload,
  payload->>'items' AS items,
  payload->>'pages' AS pages,
  payload->>'error' AS error,
  payload->>'since' AS since,
  ts
FROM accounting_audit_events
WHERE action IN ('external_sync_start', 'external_sync_success', 'external_sync_error')
ORDER BY ts DESC
LIMIT 20;
```

**확인 포인트:**
- `external_sync_start`: sync 시작 시 생성
- `external_sync_success`: 성공 시 `items`, `pages` 필드 포함
- `external_sync_error`: 실패 시 `error` 필드에 에러 메시지 포함

#### 4) 필드 존재 여부 확인 (승인)

```sql
SELECT 
  COUNT(*) AS total,
  COUNT(payload->>'top1_selected') AS has_top1_selected,
  COUNT(payload->>'selected_rank') AS has_selected_rank,
  COUNT(payload->>'ai_score') AS has_ai_score
FROM accounting_audit_events
WHERE action = 'approval_apply'
  AND ts >= NOW() - INTERVAL '24 hours';
```

**확인 포인트:**
- `has_top1_selected`, `has_selected_rank`, `has_ai_score`가 `total`과 같거나 비슷해야 함
- 0이면 필드가 누락된 것

#### 5) 필드 존재 여부 확인 (Manual Review)

```sql
SELECT 
  COUNT(*) AS total,
  COUNT(payload->>'reason_code') AS has_reason_code,
  COUNT(payload->>'amount') AS has_amount,
  COUNT(payload->>'currency') AS has_currency,
  COUNT(payload->>'is_high_value') AS has_is_high_value
FROM accounting_audit_events
WHERE action = 'manual_review_request'
  AND ts >= NOW() - INTERVAL '24 hours';
```

**확인 포인트:**
- 모든 필드가 `total`과 비슷한 값이어야 함

---

## 3. 전체 쿼리 파일 실행

```bash
# SQL 파일 전체 실행
psql $DATABASE_URL -f scripts/check_audit_events.sql
```

---

## 4. 트러블슈팅

### 이벤트가 보이지 않는 경우

1. **테넌트 확인**
   ```sql
   SELECT DISTINCT tenant FROM accounting_audit_events ORDER BY tenant;
   ```
   - 기본 테넌트는 `default` 또는 `pilot-a`

2. **최근 이벤트 확인**
   ```sql
   SELECT action, COUNT(*) 
   FROM accounting_audit_events 
   WHERE ts >= NOW() - INTERVAL '1 hour'
   GROUP BY action;
   ```

3. **payload 전체 확인**
   ```sql
   SELECT action, payload, ts
   FROM accounting_audit_events
   WHERE action IN ('approval_apply', 'manual_review_request', 'external_sync_start')
   ORDER BY ts DESC
   LIMIT 5;
   ```

### 필드가 NULL인 경우

- 클라이언트 코드에서 필드를 전송하지 않았을 수 있음
- BFF 코드에서 payload에 필드를 추가하지 않았을 수 있음
- 코드 변경 후 재배포/재시작이 필요할 수 있음

