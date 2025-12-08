# Manual Review API 문서

## 개요

Manual Review API는 고위험 거래의 수동 검토 워크플로우를 관리하는 엔드포인트입니다.

## 엔드포인트

### 1. Manual Review 목록 조회

**엔드포인트**: `GET /v1/accounting/manual-review`

**헤더**:
- `X-Tenant`: 테넌트 ID (필수)
- `X-User-Role`: 사용자 역할 (operator, auditor, admin)
- `X-User-Id`: 사용자 ID
- `X-Api-Key`: API 키

**쿼리 파라미터**:
- `status` (선택): `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED`
- `page` (선택): 페이지 번호 (기본값: 1)
- `page_size` (선택): 페이지 크기 (기본값: 50)
- `offset` (선택): 오프셋 (page와 함께 사용 가능)

**응답 예시**:
```json
{
  "items": [
    {
      "id": 1,
      "posting_id": "p-high-1",
      "risk_level": "HIGH",
      "reasons": ["HIGH_VALUE"],
      "source": "HUD",
      "status": "PENDING",
      "assignee": null,
      "note": null,
      "created_at": "2025-12-08T01:00:00Z",
      "updated_at": "2025-12-08T01:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "offset": 0,
    "has_more": false,
    "next_page": null
  }
}
```

### 2. Manual Review 상세 조회

**엔드포인트**: `GET /v1/accounting/manual-review/:id`

**헤더**: 위와 동일

**응답 예시**:
```json
{
  "id": 1,
  "posting_id": "p-high-1",
  "risk_level": "HIGH",
  "reasons": ["HIGH_VALUE", "LOW_CONFIDENCE"],
  "source": "HUD",
  "status": "PENDING",
  "assignee": null,
  "note": null,
  "created_at": "2025-12-08T01:00:00Z",
  "updated_at": "2025-12-08T01:00:00Z"
}
```

**에러 응답** (404):
```json
{
  "error_code": "NOT_FOUND",
  "message": "Manual review item not found: id=999"
}
```

### 3. Manual Review 상태 변경

**엔드포인트**: `POST /v1/accounting/manual-review/:id/resolve`

**권한**: `auditor` 이상

**헤더**: 위와 동일

**요청 본문**:
```json
{
  "status": "APPROVED",
  "note": "승인 완료 - 정상 거래로 확인됨"
}
```

또는

```json
{
  "status": "REJECTED",
  "note": "거절 - 의심스러운 거래 패턴"
}
```

**응답 예시**:
```json
{
  "id": 1,
  "posting_id": "p-high-1",
  "risk_level": "HIGH",
  "reasons": ["HIGH_VALUE"],
  "source": "HUD",
  "status": "APPROVED",
  "assignee": "admin-1",
  "note": "승인 완료 - 정상 거래로 확인됨",
  "created_at": "2025-12-08T01:00:00Z",
  "updated_at": "2025-12-08T01:30:00Z"
}
```

**에러 응답** (400):
```json
{
  "error_code": "INVALID_REQUEST",
  "message": "status must be APPROVED or REJECTED"
}
```

**에러 응답** (404):
```json
{
  "error_code": "NOT_FOUND",
  "message": "Manual review item not found: id=999"
}
```

## 상태 머신

Manual Review 항목은 다음 4가지 상태만 가질 수 있습니다:

1. **PENDING**: 수동 검토 대기 중
2. **IN_REVIEW**: 검토 중 (현재는 사용하지 않지만, 향후 확장 가능)
3. **APPROVED**: 승인됨
4. **REJECTED**: 거절됨

## Typical Flow

### 1. HUD에서 수동 검토 요청

```bash
# HUD에서 HIGH Risk 거래에 대해 수동 검토 요청
POST /v1/accounting/audit/manual-review
{
  "subject_type": "posting",
  "subject_id": "p-high-1",
  "reason": "고위험 거래로 인한 수동 검토 요청",
  "reason_code": "HIGH_VALUE",
  "amount": 1500000,
  "currency": "KRW",
  "is_high_value": true
}
```

→ `accounting_manual_review_queue`에 `PENDING` 상태로 추가됨

### 2. Backoffice에서 큐 조회

```bash
GET /v1/accounting/manual-review?status=PENDING
```

### 3. 상세 조회 및 검토

```bash
GET /v1/accounting/manual-review/1
```

### 4. 승인/거절 처리

```bash
POST /v1/accounting/manual-review/1/resolve
{
  "status": "APPROVED",
  "note": "정상 거래로 확인"
}
```

## 에러 코드

- `NOT_FOUND`: Manual Review 항목을 찾을 수 없음
- `INVALID_REQUEST`: 잘못된 요청 (예: status 값이 잘못됨)
- `INVALID_STATUS`: status 파라미터가 유효하지 않음 (PENDING, IN_REVIEW, APPROVED, REJECTED 중 하나여야 함)

## 참고

- Manual Review 항목은 HUD에서 `POST /v1/accounting/audit/manual-review`를 호출할 때 자동으로 생성됩니다.
- Risk Score가 있는 posting에 대해서만 Manual Review 큐에 추가됩니다.
- `auditor` 권한이 있어야 상태 변경(`/resolve`)이 가능합니다.

