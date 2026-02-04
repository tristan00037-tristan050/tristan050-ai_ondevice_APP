# 회계 보안 매핑

R6 회계 확장 - PII/암호화/보존/Export 정책 매핑

## PII 범위 정의

회계 도메인에서 다루는 민감 정보:

| 항목 | 저장 여부 | 저장 시 암호화 | Export 시 레드랙션 | 비고 |
|------|-----------|----------------|-------------------|------|
| **계좌번호 (은행)** | 부분 저장 (뒤 4자리만) | 예 (AES-256-GCM) | 예 (앞 6자리 마스킹) | 예: `123-456-****-7890` |
| **카드번호** | 비저장 (토큰화) | N/A | 예 (앞/뒤 4자리만 표시) | 예: `1234-****-****-5678` |
| **사업자등록번호** | 저장 | 예 (AES-256-GCM) | 예 (중간 3자리 마스킹) | 예: `123-45-***-6789` |
| **세금번호** | 저장 | 예 (AES-256-GCM) | 예 (중간 3자리 마스킹) | 예: `123-45-***-6789` |
| **이메일** | 저장 | 예 (AES-256-GCM) | 예 (로컬 파트 마스킹) | 예: `u***@example.com` |
| **전화번호** | 저장 | 예 (AES-256-GCM) | 예 (중간 4자리 마스킹) | 예: `010-****-5678` |
| **사업장 주소** | 저장 | 예 (AES-256-GCM) | 예 (상세 주소 마스킹) | 예: `서울시 강남구 ***` |

---

## 저장 정책

### 데이터베이스 저장

- **암호화**: AES-256-GCM
- **암호화 키**: `ENCRYPTION_KEY` 환경 변수 (Kubernetes Secret)
- **저장 위치**: PostgreSQL (JSONB 필드 또는 별도 암호화 컬럼)

### 부분 저장

- **계좌번호**: 뒤 4자리만 저장 (예: `****-7890`)
- **카드번호**: 토큰화 (원본 미저장)

---

## Export 정책

### 레드랙션 규칙

Export 시 다음 규칙 적용:

1. **계좌번호**: `123-456-7890-1234` → `123-456-****-1234`
2. **카드번호**: `1234-5678-9012-3456` → `1234-****-****-3456`
3. **사업자등록번호**: `123-45-678-9012` → `123-45-***-9012`
4. **세금번호**: `123-45-678-9012` → `123-45-***-9012`
5. **이메일**: `user@example.com` → `u***@example.com`
6. **전화번호**: `010-1234-5678` → `010-****-5678`
7. **주소**: `서울시 강남구 테헤란로 123` → `서울시 강남구 ***`

### Export 제한

- **최대 기간**: 90일
- **최대 레코드 수**: 10,000건
- **Export 빈도**: 일 1회 (Rate Limit)

---

## 보존 정책

### 데이터 보존 기간

- **분개 데이터**: 7년 (세법 준수)
- **승인 이력**: 7년
- **Export 매니페스트**: 1년

### 자동 삭제

- `RETAIN_DAYS` 환경 변수로 설정
- Retention 작업: `/admin/retention/run` (admin 권한)

---

## 암호화 구현

### 저장 시 암호화

```typescript
// 예시: 계좌번호 암호화
import { encrypt } from '../utils/encryption';

const encryptedAccount = encrypt(accountNumber, process.env.ENCRYPTION_KEY);
```

### 복호화

```typescript
// 예시: 계좌번호 복호화 (권한 있는 사용자만)
import { decrypt } from '../utils/encryption';

const decryptedAccount = decrypt(encryptedAccount, process.env.ENCRYPTION_KEY);
```

---

## 레드랙션 규칙 (redact_rules.json)

회계 도메인 전용 레드랙션 규칙:

```json
{
  "rules": [
    {
      "name": "account_number",
      "pattern": "\\b\\d{3,4}-\\d{3,4}-\\d{4,6}-\\d{4}\\b",
      "replacement": "$1-$2-****-$4",
      "flags": "g"
    },
    {
      "name": "card_number",
      "pattern": "\\b\\d{4}-\\d{4}-\\d{4}-\\d{4}\\b",
      "replacement": "$1-****-****-$4",
      "flags": "g"
    },
    {
      "name": "business_registration_number",
      "pattern": "\\b\\d{3}-\\d{2}-\\d{3}-\\d{4}\\b",
      "replacement": "$1-$2-***-$4",
      "flags": "g"
    },
    {
      "name": "tax_number",
      "pattern": "\\b\\d{3}-\\d{2}-\\d{3}-\\d{4}\\b",
      "replacement": "$1-$2-***-$4",
      "flags": "g"
    },
    {
      "name": "email",
      "pattern": "\\b([a-zA-Z0-9])[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})\\b",
      "replacement": "$1***@$2",
      "flags": "g"
    },
    {
      "name": "phone_number",
      "pattern": "\\b(\\d{2,3})-\\d{4}-(\\d{4})\\b",
      "replacement": "$1-****-$2",
      "flags": "g"
    }
  ]
}
```

---

## 감사 로그

### 기록 항목

- 분개 생성/수정/삭제
- 승인 요청/승인/거부
- Export 요청/다운로드
- PII 접근 (복호화)

### 로그 형식

```json
{
  "timestamp": "2025-01-20T10:30:00Z",
  "event": "posting_created",
  "tenant_id": "default",
  "user_id": "user-123",
  "posting_id": "posting-456",
  "pii_accessed": false
}
```

---

## 참고

- R5d~5.4 기준선 준수:
  - 테넌트 격리
  - 역할 가드 (viewer/operator/auditor/admin)
  - 키/토큰 비영구화
  - 감사 로그


