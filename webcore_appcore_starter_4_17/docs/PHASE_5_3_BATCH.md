# Phase 5.3 다음 배치 작업 구현

이 문서는 Phase 5.3 다음 배치 작업의 구현 내용을 설명합니다.

## ✅ 구현 완료 항목

### 1. 앱 런타임 Ajv 검증 상향

**파일**: `packages/app-expo/src/lib/validateReportFull.ts`

경량 검증(`validateReportLite`)을 Ajv 풀 검증으로 교체했습니다.

**주요 기능**:
- Ajv를 사용한 완전한 JSON Schema 검증
- `ajv-formats`를 통한 날짜/시간 형식 검증
- 비동기 스키마 로딩 (React Native 환경 지원)
- 상세한 에러 메시지 제공

**API**:
```typescript
// 풀 검증 (에러 상세 정보 포함)
const result = await validateReportFull(report);
if (!result.valid) {
  console.error('Validation errors:', result.errors);
}

// 간편 검증 (boolean만)
const isValid = await isValidReport(report);

// 에러 메시지 배열
const messages = await validateReportWithMessages(report);
```

**사용 예시**:
```typescript
import { validateReportFull, isValidReport } from './lib/validateReportFull';

// 리포트 생성 후 검증
const report = {
  status: { api: 'pass', jwks: 'pass', ... },
  diff: {},
  policy: {},
  notes: [],
  raw: {},
};

const isValid = await isValidReport(report);
if (!isValid) {
  const result = await validateReportFull(report);
  console.error('Invalid report:', result.errors);
}
```

### 2. 업로더 지연 전송 정책

**파일**: `packages/app-expo/src/lib/uploader.ts`

지수 백오프, 최대 시도, 네트워크 상태 연계 기능을 구현했습니다.

**주요 기능**:
- **지수 백오프**: 재시도 간격이 지수적으로 증가 (기본: 1초 → 2초 → 4초 → ...)
- **최대 재시도**: 기본 5회, 설정 가능
- **네트워크 상태 확인**: `@react-native-community/netinfo` 연계
- **큐 관리**: 실패한 업로드를 AsyncStorage에 저장하여 나중에 재시도
- **플러시 기능**: 큐에 쌓인 모든 항목을 일괄 재시도

**API**:
```typescript
import { uploadReport, flushQueue, getQueueStatus } from './lib/uploader';

// 리포트 업로드 (즉시 시도, 실패 시 큐에 추가)
const result = await uploadReport(report, {
  collectorUrl: 'https://collector.example.com',
  apiKey: 'your-api-key',
  tenantId: 'tenant-1',
  maxRetries: 5,
  initialBackoffMs: 1000,
  maxBackoffMs: 30000,
  backoffMultiplier: 2,
  checkNetworkState: true,
});

if (result.queued) {
  console.log('Report queued for later upload');
}

// 큐 플러시 (재시도)
const flushResult = await flushQueue(options);
console.log(`Success: ${flushResult.success}, Failed: ${flushResult.failed}`);

// 큐 상태 확인
const status = await getQueueStatus();
console.log(`Queue size: ${status.count}`);
```

**백오프 계산**:
```
재시도 1: 1초 대기
재시도 2: 2초 대기
재시도 3: 4초 대기
재시도 4: 8초 대기
재시도 5: 16초 대기 (최대 30초로 제한)
```

**네트워크 상태 연계**:
- 업로드 전 네트워크 연결 상태 확인
- 오프라인 상태에서는 즉시 큐에 추가
- 네트워크 복구 후 `flushQueue()` 호출로 재시도

**의존성**:
```json
{
  "dependencies": {
    "@react-native-community/netinfo": "^11.0.0",
    "@react-native-async-storage/async-storage": "^1.19.0"
  }
}
```

### 3. Collector /reports 응답에 ETag/If-None-Match 도입

**파일**: `packages/collector-node-ts/src/routes/reports.ts`

ETag/If-None-Match를 지원하여 폴링 비용을 절감했습니다.

**주요 기능**:
- **ETag 생성**: 응답 콘텐츠의 MD5 해시 기반 ETag 생성
- **If-None-Match 지원**: 클라이언트가 이전 ETag를 보내면 304 Not Modified 응답
- **캐시 제어**: `Cache-Control: private, must-revalidate` 헤더 설정
- **목록 및 상세 조회 모두 지원**: GET /reports, GET /reports/:id

**API 엔드포인트**:

1. **GET /reports** - 리포트 목록 조회
   ```http
   GET /reports HTTP/1.1
   X-Tenant: tenant-1
   If-None-Match: "abc123..."
   
   HTTP/1.1 304 Not Modified
   ETag: "abc123..."
   ```

2. **GET /reports/:id** - 리포트 상세 조회
   ```http
   GET /reports/123 HTTP/1.1
   X-Tenant: tenant-1
   If-None-Match: "def456..."
   
   HTTP/1.1 200 OK
   ETag: "def456..."
   Cache-Control: private, must-revalidate
   ```

**클라이언트 사용 예시**:
```typescript
// 첫 번째 요청
const response1 = await fetch('https://collector.example.com/reports', {
  headers: {
    'X-Tenant': 'tenant-1',
  },
});
const etag = response1.headers.get('ETag');
const reports = await response1.json();

// 두 번째 요청 (변경 없으면 304)
const response2 = await fetch('https://collector.example.com/reports', {
  headers: {
    'X-Tenant': 'tenant-1',
    'If-None-Match': etag,
  },
});

if (response2.status === 304) {
  console.log('No changes - use cached data');
} else {
  const newReports = await response2.json();
  const newETag = response2.headers.get('ETag');
}
```

**효과**:
- 폴링 시 변경이 없으면 전체 응답 본문을 전송하지 않음
- 네트워크 대역폭 절감
- 서버 부하 감소
- 클라이언트 캐시 효율성 향상

## 📦 통합 가이드

### 앱에서 사용하기

1. **리포트 검증**:
```typescript
import { validateReportFull } from './lib/validateReportFull';

const report = await generateReport();
const validation = await validateReportFull(report);
if (!validation.valid) {
  console.error('Report validation failed:', validation.errors);
  return;
}
```

2. **리포트 업로드**:
```typescript
import { uploadReport, flushQueue } from './lib/uploader';

// 리포트 업로드
const result = await uploadReport(report, {
  collectorUrl: process.env.COLLECTOR_URL,
  apiKey: process.env.API_KEY,
  tenantId: getTenantId(),
});

// 네트워크 복구 시 큐 플러시
NetInfo.addEventListener(state => {
  if (state.isConnected) {
    flushQueue(options);
  }
});
```

3. **ETag를 활용한 폴링**:
```typescript
let lastETag: string | null = null;

async function pollReports() {
  const headers: Record<string, string> = {
    'X-Tenant': getTenantId(),
  };
  
  if (lastETag) {
    headers['If-None-Match'] = lastETag;
  }
  
  const response = await fetch(`${collectorUrl}/reports`, { headers });
  
  if (response.status === 304) {
    // 변경 없음 - 캐시된 데이터 사용
    return;
  }
  
  lastETag = response.headers.get('ETag');
  const reports = await response.json();
  // 리포트 목록 업데이트
}
```

## 🔧 설정

### 업로더 설정

```typescript
const uploadOptions = {
  collectorUrl: 'https://collector.example.com',
  apiKey: process.env.COLLECTOR_API_KEY,
  tenantId: process.env.TENANT_ID,
  maxRetries: 5,              // 최대 재시도 횟수
  initialBackoffMs: 1000,     // 초기 백오프 (1초)
  maxBackoffMs: 30000,        // 최대 백오프 (30초)
  backoffMultiplier: 2,       // 백오프 배수
  checkNetworkState: true,    // 네트워크 상태 확인
};
```

### Collector 환경 변수

```bash
EXPORT_SIGN_SECRET=your-secret-key  # 리포트 서명용 시크릿
```

## 🧪 테스트

### 검증 테스트
```typescript
import { validateReportFull } from './lib/validateReportFull';

// 유효한 리포트
const validReport = { status: {...}, diff: {}, policy: {}, notes: [], raw: {} };
const result = await validateReportFull(validReport);
console.assert(result.valid === true);

// 무효한 리포트
const invalidReport = { status: {} }; // 필수 필드 누락
const result2 = await validateReportFull(invalidReport);
console.assert(result2.valid === false);
console.assert(result2.errors!.length > 0);
```

### 업로더 테스트
```typescript
import { uploadReport, flushQueue } from './lib/uploader';

// 정상 업로드
const result = await uploadReport(report, options);
console.assert(result.success === true);

// 네트워크 오류 시뮬레이션 (Collector 중단)
// 업로드 실패 → 큐에 추가 확인
const result2 = await uploadReport(report, { ...options, collectorUrl: 'http://invalid' });
console.assert(result2.queued === true);

// 큐 플러시
const flushResult = await flushQueue(options);
console.log(`Flushed: ${flushResult.success} success, ${flushResult.failed} failed`);
```

### ETag 테스트
```bash
# 첫 번째 요청
curl -H "X-Tenant: tenant-1" http://localhost:9090/reports -v
# ETag 헤더 확인

# 두 번째 요청 (If-None-Match 포함)
curl -H "X-Tenant: tenant-1" \
     -H "If-None-Match: \"abc123...\"" \
     http://localhost:9090/reports -v
# 304 Not Modified 응답 확인
```

## 📝 참고사항

1. **스키마 로딩**: React Native 환경에서는 스키마 파일을 번들에 포함하거나 런타임에 로드해야 합니다.
2. **네트워크 상태**: `@react-native-community/netinfo`는 네이티브 모듈이므로 링크가 필요할 수 있습니다.
3. **큐 저장소**: AsyncStorage는 비동기이므로 성능을 고려하여 배치 처리하는 것이 좋습니다.
4. **ETag 형식**: ETag는 따옴표로 감싸진 문자열 형식이어야 합니다 (예: `"abc123"`).

## 🚀 다음 단계

이제 다음 작업을 진행할 수 있습니다:

1. 실제 모노레포 구조에 맞게 경로 조정
2. 데이터베이스 연동 (Collector의 인메모리 저장소 → 실제 DB)
3. JWT 기반 서명 토큰 구현
4. ZIP 번들 생성 로직 구현
5. 통합 테스트 작성

