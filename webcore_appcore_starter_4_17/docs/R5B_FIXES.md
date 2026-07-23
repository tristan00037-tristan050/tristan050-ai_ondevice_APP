# R5b P0/P1 보완 사항 구현 완료

이 문서는 R5b 번들의 P0/P1 보완 사항 구현 내용을 설명합니다.

## ✅ P0 필수 항목

### [P0-1] 업로더 큐 보안 강화

**파일**: `packages/app-expo/src/lib/uploader.ts`

**변경 사항**:
- **API Key 저장 금지**: 큐에 API Key를 저장하지 않음
- **큐 원소 구조 변경**: `report`, `md`(레드랙션 적용), `tenantId`, `attempt`, `createdAt`만 저장
- **API Key는 메모리/옵션으로만 사용**: 업로드/플러시 시에만 헤더에 주입

**구현**:
```typescript
export interface QueuedItem {
  id: string;
  report: unknown;
  md?: string; // 레드랙션 적용된 마크다운 (옵션)
  tenantId: string; // 테넌트 ID만 저장 (API Key는 저장하지 않음)
  attempt: number; // 재시도 횟수
  createdAt: number; // 생성 시각
  lastError?: string;
}
```

### [P0-2] Collector 테넌트/권한 가드 강제

**파일**: 
- `packages/collector-node-ts/src/mw/auth.ts` (인증 미들웨어)
- `packages/collector-node-ts/src/index.ts` (서버 진입점)
- `packages/collector-node-ts/src/routes/reports.ts` (Reports 라우터)

**변경 사항**:
- **API_KEYS 환경변수 매핑**: `"default:collector-key,teamA:teamA-key"` 형식으로 테넌트 ↔ API Key 매핑
- **모든 엔드포인트에 가드 적용**:
  - `GET /reports` - requireTenantAuth
  - `GET /reports/:id` - requireTenantAuth
  - `POST /reports/:id/sign` - requireTenantAuth
  - `GET /reports/:id/bundle.zip` - verifySignToken (서명 토큰 검증 + tenant/id 교차검증)
  - `GET /timeline` - requireTenantAuth
  - `POST /ingest/qc` - requireTenantAuth
  - `POST /admin/retention/run` - requireTenantAuth

**구현**:
```typescript
// API_KEYS 환경변수 파싱
function parseApiKeys(): Map<string, string> {
  const apiKeysStr = process.env.API_KEYS || 'default:collector-key';
  const map = new Map<string, string>();
  
  for (const pair of apiKeysStr.split(',')) {
    const [tenant, key] = pair.split(':').map(s => s.trim());
    if (tenant && key) {
      map.set(tenant, key);
    }
  }
  
  return map;
}

// 테넌트/API Key 검증 미들웨어
export function requireTenantAuth(req, res, next) {
  const tenantId = req.headers['x-tenant'];
  const apiKey = req.headers['x-api-key'];
  
  // API 키 맵에서 테넌트에 해당하는 키 확인
  const expectedKey = keyMap.get(tenantId);
  
  if (apiKey !== expectedKey) {
    res.status(403).json({ error: 'Invalid API key for tenant' });
    return;
  }
  
  req.tenantId = tenantId;
  next();
}
```

## ✅ P1 권고 항목

### [P1] 업로더 지터(Jitter) + NetInfo 리스너 가드

**파일**: `packages/app-expo/src/lib/uploader.ts`

**변경 사항**:
- **지터 추가**: 지수 백오프에 ±1초 지터 추가하여 동시 재시도 분산
- **NetInfo 리스너 가드**: `ensureNetinfoFlusher()`로 리스너 중복 등록 방지

**구현**:
```typescript
// 지터 포함 백오프 계산
function calculateBackoff(retryCount, initialBackoffMs, maxBackoffMs, multiplier) {
  const backoff = initialBackoffMs * Math.pow(multiplier, retryCount);
  const clamped = Math.min(backoff, maxBackoffMs);
  // ±1초 지터 추가 (동시 재시도 분산)
  const jitter = (Math.random() * 2000) - 1000; // -1000ms ~ +1000ms
  return Math.max(0, clamped + jitter);
}

// NetInfo 리스너 중복 등록 방지
let isNetInfoListenerRegistered = false;

export function ensureNetinfoFlusher(options) {
  if (isNetInfoListenerRegistered) {
    return; // 이미 등록됨
  }
  
  NetInfo.addEventListener(state => {
    if (state.isConnected) {
      flushQueue(options);
    }
  });
  
  isNetInfoListenerRegistered = true;
}
```

### [P1] Ajv 런타임 검증 상향 & 인스턴스 재사용

**파일**: `packages/app-expo/src/lib/validateReportFull.ts`

**변경 사항**:
- **Ajv 싱글턴 재사용**: 인스턴스를 한 번만 생성하여 재사용
- **RN 번들에서 스키마 require**: React Native 환경에서 스키마 로드
- **schema_version 필드 도입**: 스키마 불일치 탐지 대비 (옵션)

**구현**:
```typescript
// Ajv 싱글턴 인스턴스 (재사용)
const ajv = new Ajv({
  allErrors: true,
  verbose: true,
  strict: true,
  validateFormats: true,
  removeAdditional: false,
});
addFormats(ajv);

// 스키마 컴파일 (지연 로딩, 싱글턴)
let validate: Ajv.ValidateFunction | null = null;

async function getValidator(): Promise<Ajv.ValidateFunction> {
  if (validate) {
    return validate; // 재사용
  }
  
  const schema = await loadSchema();
  validate = ajv.compile(schema);
  return validate;
}
```

### [P1] ETag 안정성/304 최적화

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

**변경 사항**:
- **목록 정렬 고정**: ID/시각 기준으로 정렬 고정하여 ETag MD5 안정화
- **Cache-Control 헤더 유지**: `private, must-revalidate`

**구현**:
```typescript
// 정렬 고정: 먼저 createdAt 내림차순, 같으면 id 오름차순
const tenantReports = Array.from(reports.values())
  .filter(r => r.tenantId === tenantId)
  .map(r => ({
    id: r.id,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt,
  }))
  .sort((a, b) => {
    if (b.createdAt !== a.createdAt) {
      return b.createdAt - a.createdAt;
    }
    return a.id.localeCompare(b.id);
  });

// ETag 생성 (정렬 고정으로 안정성 보장)
const content = JSON.stringify(tenantReports);
const etag = generateETag(content);
```

### [P1] /reports/:id/sign 멱등성

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

**변경 사항**:
- **멱등성 보장**: 유효기간 내 동일 요청 시 기존 토큰 재사용
- **서명 토큰에 tenant 포함**: 토큰 페이로드에 tenant 포함
- **/bundle.zip에서 tenant/id 교차검증**: 토큰 검증 후 tenant/id 매칭 재검증

**구현**:
```typescript
// 서명 토큰 캐시 (멱등성 보장)
const signTokenCache = new Map<string, { token: string; expiresAt: number }>();

router.post('/:id/sign', requireTenantAuth, async (req, res) => {
  const cacheKey = `${tenantId}:${id}`;
  const cached = signTokenCache.get(cacheKey);
  
  // 유효기간 내 동일 요청 시 기존 토큰 재사용 (멱등성)
  if (cached && cached.expiresAt > Date.now()) {
    return res.json({
      token: cached.token,
      expiresAt: cached.expiresAt,
      bundleUrl: `/reports/${id}/bundle.zip?token=${cached.token}`,
    });
  }
  
  // 새 토큰 생성 (tenant 포함)
  const tokenPayload = {
    reportId: id,
    tenantId, // tenant 포함
    expiresAt: Date.now() + 3600000,
  };
  
  // ... 토큰 생성 및 캐시 저장
});
```

## 📦 환경 변수 설정

### Collector

```bash
# API 키 매핑 (테넌트:키 형식)
export API_KEYS="default:collector-key,teamA:teamA-key"

# 서명 시크릿
export EXPORT_SIGN_SECRET='<read-from-local-secret-store>'

# 보존 기간 (일)
export RETAIN_DAYS=30
```

### App

```typescript
// .env 또는 안전 채널로 주입 (영구 저장 금지)
const CONFIG = {
  COLLECTOR_URL: 'https://collector.example.com',
  COLLECTOR_KEY: process.env.COLLECTOR_KEY, // 메모리에만 저장
  TENANT: 'default', // 팀 상수화
};

// 첫 실행 시 NetInfo 리스너 등록
ensureNetinfoFlusher({
  collectorUrl: CONFIG.COLLECTOR_URL,
  apiKey: CONFIG.COLLECTOR_KEY,
  tenantId: CONFIG.TENANT,
});
```

## 🧪 테스트 시나리오

### 큐 보안 테스트
```typescript
// API Key가 큐에 저장되지 않는지 확인
const result = await uploadReport(report, options);
const queue = await loadQueue();
const item = queue[0];

console.assert(!('apiKey' in item)); // API Key 없음
console.assert(item.tenantId === options.tenantId); // tenantId만 있음
```

### 테넌트 격리 테스트
```bash
# 올바른 테넌트/키
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     http://localhost:9090/reports

# 잘못된 키
curl -H "X-Tenant: default" \
     -H "X-Api-Key: wrong-key" \
     http://localhost:9090/reports
# 403 Forbidden 예상
```

### 멱등성 테스트
```bash
# 첫 번째 요청
TOKEN1=$(curl -X POST \
  -H "X-Tenant: default" \
  -H "X-Api-Key: collector-key" \
  http://localhost:9090/reports/report-123/sign | jq -r .token)

# 두 번째 요청 (같은 토큰 반환)
TOKEN2=$(curl -X POST \
  -H "X-Tenant: default" \
  -H "X-Api-Key: collector-key" \
  http://localhost:9090/reports/report-123/sign | jq -r .token)

# TOKEN1 === TOKEN2 확인
```

## 📝 참고사항

1. **API Key 보안**: API Key는 메모리에만 저장하고, 큐나 영구 저장소에 저장하지 않음
2. **테넌트 격리**: 모든 엔드포인트에서 테넌트 격리 보장
3. **멱등성**: 동일한 요청에 대해 동일한 응답 보장
4. **ETag 안정성**: 정렬 고정으로 ETag 값이 안정적으로 유지됨
5. **NetInfo 리스너**: 중복 등록 방지로 메모리 누수 방지

## 🚀 다음 단계

이제 다음 작업을 진행할 수 있습니다:

1. 실제 데이터베이스 연동 (인메모리 저장소 → DB)
2. JWT 기반 서명 토큰 구현
3. ZIP 번들 생성 로직 구현
4. 통합 테스트 작성
5. 리포트 조회 UI/대시보드 구현 (Phase 5.3 UI 편성)

