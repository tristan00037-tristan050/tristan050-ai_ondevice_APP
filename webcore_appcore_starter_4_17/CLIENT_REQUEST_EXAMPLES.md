# 클라이언트 요청 예시

## 1. 승인(Approval) 요청 예시

### 시나리오: 사용자가 추천 1위를 선택하여 승인

**요청 URL:**
```
POST /v1/accounting/approvals/report-123
```

**요청 Body (Top-1 선택):**
```json
{
  "action": "approve",
  "client_request_id": "req-2025-12-04-001",
  "note": "OK",
  "top1_selected": true,
  "selected_rank": 1,
  "ai_score": 0.85
}
```

### 시나리오: 사용자가 추천 3위를 선택하여 승인

**요청 Body (Top-3 선택):**
```json
{
  "action": "approve",
  "client_request_id": "req-2025-12-04-002",
  "note": "OK",
  "top1_selected": false,
  "selected_rank": 3,
  "ai_score": 0.72
}
```

### 시나리오: 반려(Reject) 요청

**요청 Body:**
```json
{
  "action": "reject",
  "client_request_id": "req-2025-12-04-003",
  "note": "잘못된 분개"
}
```

**참고:** `reject` 액션의 경우 `top1_selected`, `selected_rank`, `ai_score` 필드는 포함되지 않습니다.

---

## 2. Manual Review 요청 예시

### 시나리오: 고액 거래로 인한 수동 검토 요청

**요청 URL:**
```
POST /v1/accounting/audit/manual-review
```

**요청 Body (고액 거래):**
```json
{
  "subject_type": "posting",
  "subject_id": "posting-456",
  "reason": "수동 검토 필요",
  "reason_code": "HIGH_VALUE",
  "amount": 1500000,
  "currency": "KRW",
  "is_high_value": true
}
```

### 시나리오: 낮은 신뢰도로 인한 수동 검토 요청

**요청 Body (낮은 신뢰도):**
```json
{
  "subject_type": "posting",
  "subject_id": "posting-789",
  "reason": "수동 검토 필요",
  "reason_code": "LOW_CONFIDENCE",
  "amount": 4500,
  "currency": "KRW",
  "is_high_value": false
}
```

### 시나리오: 최소 필수 정보만 포함

**요청 Body (최소 필수):**
```json
{
  "subject_type": "posting",
  "subject_id": "posting-999",
  "reason": "수동 검토 필요"
}
```

**참고:** `reason_code`, `amount`, `currency`, `is_high_value`는 선택적 필드입니다.

---

## 3. BFF에서 받는 Audit Payload 예시

### approval_apply 이벤트

```json
{
  "tenant": "default",
  "action": "approval_apply",
  "subject_type": "report",
  "subject_id": "report-123",
  "payload": {
    "note": "OK",
    "top1_selected": true,
    "selected_rank": 1,
    "ai_score": 0.85
  }
}
```

### manual_review_request 이벤트

```json
{
  "tenant": "default",
  "action": "manual_review_request",
  "subject_type": "posting",
  "subject_id": "posting-456",
  "payload": {
    "reason": "수동 검토 필요",
    "reason_code": "HIGH_VALUE",
    "amount": 1500000,
    "currency": "KRW",
    "is_high_value": true
  }
}
```

---

## 4. 코드 흐름

### 승인 요청 흐름

1. **AccountingHUD.tsx** `onApprove()` 함수:
   - `selectedPostingIndex`로 선택된 posting index 확인 (기본값: 0)
   - `top1_selected = selectedIndex === 0`
   - `selected_rank = selectedIndex + 1`
   - `ai_score = suggestOut.confidence`

2. **accounting-api.ts** `postApproval()` 함수:
   - `approve` 액션일 때만 선택 정보를 body에 추가
   - `reject` 액션일 때는 기존 필드만 포함

3. **offline-queue.ts**:
   - 오프라인 큐에도 선택 정보를 포함하여 저장
   - 온라인 전환 시 동일한 정보로 재전송

### Manual Review 요청 흐름

1. **AccountingHUD.tsx**:
   - `desc`에서 금액 추출 (정규식으로 숫자 추출)
   - `HIGH_VALUE_THRESHOLD = 1000000` 기준으로 `isHighValue` 계산
   - `reasonCode`는 `isHighValue`에 따라 `HIGH_VALUE` 또는 `LOW_CONFIDENCE` 설정

2. **ManualReviewButton.tsx**:
   - 받은 props를 그대로 요청 body에 포함
   - 선택적 필드는 `undefined`가 아닐 때만 포함

---

## 5. 리포트 스크립트 활용

### report_pilot_metrics.mjs

**Top-1 정확도 계산:**
```sql
SELECT 
  COUNT(*) FILTER (WHERE payload->>'top1_selected' = 'true') as top1_count,
  COUNT(*) as total_approvals
FROM accounting_audit_events
WHERE action = 'approval_apply'
  AND ts >= '2025-12-01'
  AND ts < '2025-12-31'
```

**Top-5 정확도 계산:**
```sql
SELECT 
  COUNT(*) FILTER (WHERE (payload->>'selected_rank')::int <= 5) as top5_count,
  COUNT(*) as total_approvals
FROM accounting_audit_events
WHERE action = 'approval_apply'
  AND ts >= '2025-12-01'
  AND ts < '2025-12-31'
```

**Manual Review 비율 (고액 거래 기준):**
```sql
SELECT 
  COUNT(*) FILTER (WHERE payload->>'is_high_value' = 'true') as high_value_reviews,
  COUNT(*) as total_reviews
FROM accounting_audit_events
WHERE action = 'manual_review_request'
  AND ts >= '2025-12-01'
  AND ts < '2025-12-31'
```

