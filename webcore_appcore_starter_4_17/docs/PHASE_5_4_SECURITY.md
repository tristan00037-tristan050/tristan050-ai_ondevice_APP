# Phase 5.4 보안 강화

Phase 5.4 보안 강화 작업 완료 문서입니다.

## 📋 구현 완료 항목

### 1. API Rate Limiting

**파일**: `packages/collector-node-ts/src/mw/rateLimit.ts`

**구현 사항**:
- 테넌트별 요청 제한
- IP 기반 제한
- 토큰(API Key) 기반 제한
- 인메모리 저장소 (프로덕션에서는 Redis 사용 권장)
- Rate Limit 헤더 제공 (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)

**기본 설정**:
- **defaultRateLimiter**: 100 requests/minute
- **strictRateLimiter**: 10 requests/minute
- **looseRateLimiter**: 1000 requests/minute

**사용 예시**:
```typescript
import { defaultRateLimiter, strictRateLimiter } from './mw/rateLimit.js';

// 기본 Rate Limiter 적용
app.use(defaultRateLimiter);

// 특정 엔드포인트에 엄격한 Rate Limiter 적용
app.post('/admin/retention/run', strictRateLimiter, requireTenantAuth, handler);
```

**응답 형식 (429 Too Many Requests)**:
```json
{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Maximum 100 requests per 60 seconds.",
  "retryAfter": 45
}
```

---

### 2. 감사 로그 강화

**파일**: `packages/collector-node-ts/src/mw/audit.ts`

**구현 사항**:
- 모든 API 요청 로깅
- 보안 이벤트 감지 및 로깅
- 테넌트별, 시간 범위별 필터링
- 관리자용 감사 로그 조회 API

**보안 이벤트 타입**:
- `rate_limit`: Rate limit 초과
- `unauthorized`: 인증 실패 (401)
- `forbidden`: 권한 없음 (403)
- `invalid_input`: 잘못된 입력 (400)
- `suspicious_activity`: 의심스러운 활동 (SQL Injection, XSS 시도 등)

**감사 로그 형식**:
```typescript
interface AuditLog {
  timestamp: number;
  method: string;
  path: string;
  tenantId?: string;
  ip: string;
  userAgent?: string;
  statusCode: number;
  responseTime: number;
  error?: string;
  securityEvent?: {
    type: 'rate_limit' | 'unauthorized' | 'forbidden' | 'invalid_input' | 'suspicious_activity';
    details: string;
  };
}
```

**API 엔드포인트**: `GET /admin/audit/logs`
- Query Parameters:
  - `start_time`: 시작 시간 (타임스탬프)
  - `end_time`: 종료 시간 (타임스탬프)
  - `security_event`: 보안 이벤트만 조회 (true/false)
  - `limit`: 최대 조회 개수 (기본 100)

---

### 3. 입력 검증 강화

**파일**: `packages/collector-node-ts/src/mw/validation.ts`

**구현 사항**:
- SQL Injection 방지
- XSS 방지
- 문자열 길이 제한 검증
- 숫자 범위 검증
- ID 형식 검증

**검증 패턴**:
- **SQL Injection**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `--`, `;`, `/*`, `*/` 등
- **XSS**: `<script>`, `<iframe>`, `javascript:`, `onclick`, `onerror` 등

**사용 예시**:
```typescript
import { validateInput, validateIdFormat, validateStringLength } from './mw/validation.js';

// 미들웨어로 적용
app.use(validateInput);

// 개별 검증
const idValidation = validateIdFormat(reportId);
if (!idValidation.valid) {
  return res.status(400).json({ error: idValidation.error });
}
```

---

### 4. 암호화

**파일**: `packages/collector-node-ts/src/utils/encryption.ts`

**구현 사항**:
- AES-256-GCM 암호화 (at rest)
- API Key 해싱 (SHA256)
- HMAC 서명 생성/검증
- 안전한 랜덤 문자열 생성

**암호화 함수**:
- `encrypt(data: string)`: 데이터 암호화
- `decrypt(encryptedData: string)`: 데이터 복호화
- `hashApiKey(apiKey: string)`: API Key 해싱
- `verifyApiKey(apiKey: string, hashedKey: string)`: API Key 검증
- `createHMAC(data: string, secret: string)`: HMAC 서명 생성
- `verifyHMAC(data: string, signature: string, secret: string)`: HMAC 서명 검증

**환경 변수**:
```bash
ENCRYPTION_KEY=your-encryption-key-here
```

**사용 예시**:
```typescript
import { encrypt, decrypt, hashApiKey, verifyApiKey } from './utils/encryption.js';

// 데이터 암호화
const encrypted = encrypt('sensitive data');
const decrypted = decrypt(encrypted);

// API Key 해싱
const hashedKey = hashApiKey('api-key-123');
const isValid = verifyApiKey('api-key-123', hashedKey);
```

---

## 🔒 보안 미들웨어 적용

### 전역 미들웨어

```typescript
// packages/collector-node-ts/src/index.ts
app.use(auditMiddleware); // 감사 로그
app.use(validateInput); // 입력 검증
app.use(defaultRateLimiter); // Rate Limiting
```

### 엔드포인트별 적용

```typescript
// 엄격한 Rate Limiter 적용
app.post('/admin/retention/run', strictRateLimiter, requireTenantAuth, handler);

// ID 형식 검증
router.get('/:id', requireTenantAuth, async (req, res) => {
  const idValidation = validateIdFormat(req.params.id);
  if (!idValidation.valid) {
    return res.status(400).json({ error: idValidation.error });
  }
  // ...
});
```

---

## 🚀 사용 방법

### Rate Limiting 확인

```bash
# Rate Limit 헤더 확인
curl -v http://localhost:9090/reports \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"

# 응답 헤더:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 1234567890
```

### 감사 로그 조회

```bash
# 모든 감사 로그 조회
curl http://localhost:9090/admin/audit/logs \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"

# 보안 이벤트만 조회
curl "http://localhost:9090/admin/audit/logs?security_event=true&limit=50" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
```

### 입력 검증 테스트

```bash
# SQL Injection 시도 (차단됨)
curl "http://localhost:9090/reports?id=1' OR '1'='1" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
# 응답: 400 Bad Request

# XSS 시도 (차단됨)
curl "http://localhost:9090/reports?id=<script>alert('xss')</script>" \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default"
# 응답: 400 Bad Request
```

---

## 🔧 향후 개선 사항

### Redis 기반 Rate Limiting

```typescript
// packages/collector-node-ts/src/mw/rateLimitRedis.ts
import Redis from 'ioredis';

const redis = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: parseInt(process.env.REDIS_PORT || '6379'),
});

export async function incrementRateLimit(
  key: string,
  windowMs: number
): Promise<{ count: number; resetAt: number }> {
  const now = Date.now();
  const windowKey = `ratelimit:${key}:${Math.floor(now / windowMs)}`;
  const count = await redis.incr(windowKey);
  await redis.expire(windowKey, Math.ceil(windowMs / 1000));
  return { count, resetAt: (Math.floor(now / windowMs) + 1) * windowMs };
}
```

### CSRF 보호

```typescript
// CSRF 토큰 생성 및 검증
import { generateSecureRandom } from './utils/encryption.js';

// 세션에 CSRF 토큰 저장
req.session.csrfToken = generateSecureRandom();

// 요청 시 CSRF 토큰 검증
if (req.body.csrfToken !== req.session.csrfToken) {
  return res.status(403).json({ error: 'Invalid CSRF token' });
}
```

### 데이터베이스 감사 로그 저장

```typescript
// packages/collector-node-ts/src/db/auditLogs.ts
export async function saveAuditLogToDB(log: AuditLog): Promise<void> {
  await query(
    `INSERT INTO audit_logs (timestamp, method, path, tenant_id, ip, user_agent, status_code, response_time, error, security_event_type, security_event_details)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
    [
      log.timestamp,
      log.method,
      log.path,
      log.tenantId,
      log.ip,
      log.userAgent,
      log.statusCode,
      log.responseTime,
      log.error,
      log.securityEvent?.type,
      log.securityEvent?.details,
    ]
  );
}
```

---

## 📚 참고 문서

- `docs/PHASE_5_4_KICKOFF.md` - Phase 5.4 킥오프 문서
- `packages/collector-node-ts/src/mw/rateLimit.ts` - Rate Limiting 구현
- `packages/collector-node-ts/src/mw/audit.ts` - 감사 로그 구현
- `packages/collector-node-ts/src/mw/validation.ts` - 입력 검증 구현
- `packages/collector-node-ts/src/utils/encryption.ts` - 암호화 유틸리티

---

**버전**: Phase 5.4 보안 강화 v1
**날짜**: 2025-01-XX
**상태**: ✅ 기본 보안 강화 완료


