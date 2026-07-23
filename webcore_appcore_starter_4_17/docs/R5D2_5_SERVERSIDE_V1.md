# R5d-2 ~ R5d-5 서버사이드 구현 (v1)

P0 결함(r5d-1) 수정 완료 후, r5d-2 ~ r5d-5 서버사이드 작업을 정리한 문서입니다.

## 📋 구현 완료 항목

### ✅ r5d-1: 서버 측 필터링 (P0 결함 수정)

**상태**: ✅ 완료

**엔드포인트**: `GET /reports?severity=block&policy_version=v1&since=1234567890&page=1&limit=20`

**구현 위치**: `packages/collector-node-ts/src/routes/reports.ts`

**기능**:
- Query Parameter 지원 (severity, policy_version, since, page, limit)
- 서버 측 필터링
- 서버 측 페이지네이션
- ETag 생성 (필터링 결과 기반)

**응답 형식**:
```json
{
  "reports": ReportSummary[],
  "pagination": {
    "page": 1,
    "limit": 20,
    "totalCount": 100,
    "totalPages": 5
  }
}
```

---

### ✅ r5d-2: 서명 감사 로그 (서버사이드)

**상태**: ✅ 완료

**엔드포인트**: `GET /reports/:id/sign-history`

**구현 위치**: `packages/collector-node-ts/src/routes/reports.ts`

**기능**:
- 서명 이력 저장소 (`signHistory` 배열)
- `POST /reports/:id/sign` 호출 시 자동 이력 저장
- 테넌트별 이력 필터링
- 최신순 정렬
- 토큰 미리보기 (처음 16자만 표시)
- 이력 최대 1000개 유지 (오래된 것 자동 제거)

**응답 형식**:
```json
{
  "reportId": "report-123",
  "history": [
    {
      "requestedBy": "default",
      "issuedAt": 1234567890,
      "expiresAt": 1234571490,
      "createdAt": 1234567890,
      "tokenPreview": "eyJhbGciOiJIUzI1..."
    }
  ],
  "count": 1
}
```

**보안**:
- `requireTenantAuth` 미들웨어 적용
- 테넌트 격리 보장

---

### ✅ r5d-3: 번들 메타 정보 (서버사이드)

**상태**: ✅ 완료

**엔드포인트**: `GET /reports/:id/bundle-meta`

**구현 위치**: `packages/collector-node-ts/src/routes/reports.ts`

**기능**:
- 번들 구성 파일 목록 (qc_report.json, qc_report.md)
- 파일 크기 계산 (바이트 단위)
- SHA256 체크섬 계산
- ZIP 크기 추정 (10% 오버헤드)
- 테넌트 격리 보장

**응답 형식**:
```json
{
  "reportId": "report-123",
  "files": [
    {
      "name": "qc_report.json",
      "size": 1024,
      "checksum": "abc123def456..."
    },
    {
      "name": "qc_report.md",
      "size": 2048,
      "checksum": "xyz789uvw012..."
    }
  ],
  "totalFiles": 2,
  "totalSize": 3072,
  "estimatedZipSize": 3379,
  "checksums": {
    "qc_report.json": "abc123def456...",
    "qc_report.md": "xyz789uvw012..."
  },
  "createdAt": 1234567890,
  "updatedAt": 1234567890
}
```

**보안**:
- `requireTenantAuth` 미들웨어 적용
- 테넌트 격리 보장

---

### ✅ r5d-4: 타임라인 API BLOCK 집계 (서버사이드)

**상태**: ✅ 완료

**엔드포인트**: `GET /timeline?window_h=24`

**구현 위치**: `packages/collector-node-ts/src/index.ts`

**기능**:
- 테넌트별 리포트 필터링
- 시간 범위 필터링 (window_h 기준)
- 1시간 단위 버킷 생성
- 각 버킷별 severity 집계 (info, warn, block)
- 리포트의 최고 severity 추출 (block > warn > info)

**집계 로직**:
1. 테넌트별 리포트 필터링
2. 시간 범위 내 리포트 필터링 (startTime ~ now)
3. 1시간 단위 버킷 생성
4. 각 버킷별 리포트의 최고 severity 집계
5. 버킷별 info/warn/block 카운트 반환

**응답 형식**:
```json
{
  "window_h": 24,
  "buckets": [
    {
      "time": 1234567890,
      "info": 5,
      "warn": 2,
      "block": 1
    },
    {
      "time": 1234571490,
      "info": 3,
      "warn": 1,
      "block": 0
    }
  ]
}
```

**보안**:
- `requireTenantAuth` 미들웨어 적용
- 테넌트 격리 보장

---

### ✅ r5d-5: 권한 레벨 (서버사이드)

**상태**: 클라이언트 사이드만 구현 (서버사이드 불필요)

**설명**:
- 권한 레벨은 클라이언트 사이드(ops-console)에서만 관리
- 서버사이드(Collector)는 모든 엔드포인트에 `requireTenantAuth` 적용
- 다운로드 권한은 클라이언트에서 UI 제어

---

## 🔒 보안 및 테넌트 격리

### 모든 엔드포인트 보안 적용

**인증 미들웨어**: `packages/collector-node-ts/src/mw/auth.ts`

1. **requireTenantAuth**:
   - X-Tenant 헤더 검증
   - X-Api-Key 헤더 검증
   - API_KEYS 환경변수 매핑 검증
   - 테넌트별 데이터 격리

2. **verifySignToken**:
   - 토큰 형식 검증 (base64(payload).signature)
   - 서명 검증 (HMAC-SHA256)
   - 페이로드 디코딩
   - expiresAt 검증
   - tenantId/reportId 교차검증

### 적용된 엔드포인트

- ✅ `GET /reports` - requireTenantAuth (r5d-1: 서버 측 필터링)
- ✅ `GET /reports/:id` - requireTenantAuth
- ✅ `POST /reports/:id/sign` - requireTenantAuth
- ✅ `GET /reports/:id/sign-history` - requireTenantAuth (r5d-2)
- ✅ `GET /reports/:id/bundle-meta` - requireTenantAuth (r5d-3)
- ✅ `GET /reports/:id/bundle.zip` - verifySignToken
- ✅ `GET /timeline` - requireTenantAuth (r5d-4)
- ✅ `POST /ingest/qc` - requireTenantAuth
- ✅ `POST /admin/retention/run` - requireTenantAuth

---

## 📊 API 엔드포인트 전체 목록

### Reports API
```
GET  /reports                    - 리포트 목록 (서버 측 필터링, r5d-1)
GET  /reports/:id                - 리포트 상세
POST /reports/:id/sign           - 리포트 서명 (멱등성 보장)
GET  /reports/:id/sign-history   - 서명 이력 조회 (r5d-2)
GET  /reports/:id/bundle-meta    - 번들 메타 정보 (r5d-3)
GET  /reports/:id/bundle.zip     - 번들 다운로드 (토큰 검증)
```

### Timeline API
```
GET  /timeline?window_h=24       - 타임라인 조회 (severity 집계, r5d-4)
```

### 기타 API
```
GET  /                           - API 정보
GET  /health                     - Health check
POST /ingest/qc                  - 리포트 인제스트
POST /admin/retention/run        - 보존 정책 실행
```

---

## 🧪 검증 시나리오

### r5d-1: 서버 측 필터링 테스트
```bash
# severity 필터
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?severity=block&page=1&limit=20"

# policy_version 필터
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?policy_version=v1&page=1&limit=20"

# since 필터 (최근 24시간)
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/reports?since=$(($(date +%s) - 86400))000&page=1&limit=20"
```

### r5d-2: 서명 이력 조회 테스트
```bash
# 리포트 서명
curl -X POST \
  -H "X-Tenant: default" \
  -H "X-Api-Key: collector-key" \
  http://localhost:9090/reports/report-123/sign

# 서명 이력 조회
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     http://localhost:9090/reports/report-123/sign-history
```

### r5d-3: 번들 메타 정보 조회 테스트
```bash
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     http://localhost:9090/reports/report-123/bundle-meta
```

### r5d-4: 타임라인 조회 테스트
```bash
# 24시간 타임라인
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/timeline?window_h=24"

# 48시간 타임라인
curl -H "X-Tenant: default" \
     -H "X-Api-Key: collector-key" \
     "http://localhost:9090/timeline?window_h=48"
```

---

## 📦 파일 구조

### Collector 서버사이드
```
packages/collector-node-ts/
├── src/
│   ├── index.ts                 # 메인 서버, 타임라인 API (r5d-4)
│   ├── mw/
│   │   └── auth.ts              # 인증 미들웨어
│   └── routes/
│       └── reports.ts           # Reports API (r5d-1, r5d-2, r5d-3)
└── dist/                        # 빌드 산출물
```

### Ops Console 클라이언트사이드
```
packages/ops-console/
├── src/
│   ├── api/
│   │   ├── client.ts            # ETag 캐시 클라이언트
│   │   └── reports.ts           # API 래퍼 (서버 측 필터링 지원)
│   ├── components/
│   │   ├── SignHistory.tsx      # 서명 이력 UI (r5d-2)
│   │   ├── BundleMeta.tsx       # 번들 메타 UI (r5d-3)
│   │   ├── BlockAlert.tsx       # BLOCK 급증 알림 (r5d-4)
│   │   └── ProtectedRoute.tsx   # 권한 가드 (r5d-5)
│   ├── pages/
│   │   ├── Reports.tsx          # 리포트 목록 (서버 측 필터링, r5d-1)
│   │   ├── ReportDetail.tsx     # 리포트 상세
│   │   └── Timeline.tsx         # 타임라인
│   └── contexts/
│       └── AuthContext.tsx      # 권한 컨텍스트 (r5d-5)
```

---

## ✅ 최종 검증 결과

### 서버사이드 (Collector)
- ✅ r5d-1: 서버 측 필터링 구현 완료
- ✅ r5d-2: 서명 이력 저장/조회 API 완료
- ✅ r5d-3: 번들 메타 정보 API 완료
- ✅ r5d-4: 타임라인 API severity 집계 완료
- ✅ 모든 API 엔드포인트 테넌트 격리 보장
- ✅ 토큰 검증 로직 완료 (페이로드 디코딩 및 교차검증)
- ✅ TypeScript 빌드 성공
- ✅ Lint 오류 없음

### 클라이언트사이드 (Ops Console)
- ✅ r5d-1: 클라이언트 측 필터링 제거, API 재호출 구현
- ✅ 모든 UI 컴포넌트 구현 완료
- ✅ ESLint 경고 0개
- ✅ TypeScript 오류 0개
- ✅ ETag 캐시 최적화 완료

---

## 🔒 불변 원칙 준수

1. **웹 코어 기준선 고정**: web-core-4.17.0(4054c04) 유지보수 모드
2. **정책/리포트 스키마 준수**: Ajv 검증(앱/Collector), CI 스키마 게이트 유지
3. **라벨 화이트리스트**: decision|ok 유지
4. **오프라인 우선**: 앱 업로더 큐(민감정보 미저장), 지수 백오프+지터
5. **테넌트 격리**: Collector 전 엔드포인트 강제 가드 + /bundle.zip 토큰 교차검증
6. **ETag 최적화**: 목록 정렬 고정/MD5 ETag 안정화, UI 304 활용
7. **OpenAPI/타입**: BFF/Collector 명세 → 타입 생성/동기화

---

## 📝 환경 변수 설정

### Collector
```bash
# API 키 매핑 (테넌트:키 형식)
export API_KEYS="default:collector-key,teamA:teamA-key"

# 서명 시크릿
export EXPORT_SIGN_SECRET='<read-from-local-secret-store>'

# 보존 기간 (일)
export RETAIN_DAYS=30
```

### Ops Console
```bash
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=collector-key
VITE_TENANT=default
VITE_PERMISSION=download  # 'read-only' 또는 'download'
```

---

## 🚀 실행 방법

### 1. Collector 기동
```bash
cd packages/collector-node-ts
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET='<read-from-local-secret-store>'
export RETAIN_DAYS=30
npm install
npm run build
npm start
# http://localhost:9090
```

### 2. Ops Console 기동
```bash
cd packages/ops-console
npm install
cp env.example .env
# .env 파일 수정
npm run dev
# http://localhost:5173
```

---

## 📚 관련 문서

- `docs/P0_R5D1_FIX.md` - P0 결함 수정 상세
- `docs/R5D_SERVER_REVIEW.md` - 서버사이드 기준 검토
- `docs/R5B_FIXES.md` - R5b P0/P1 보완 사항
- `docs/PHASE_5_3_UI.md` - UI DoR/DoD, 운영 체크리스트

---

## ✅ 완료 확인

**R5d-2 ~ R5d-5 서버사이드 구현 (v1)** - 모든 작업 완료

- ✅ r5d-1: 서버 측 필터링 (P0 결함 수정)
- ✅ r5d-2: 서명 감사 로그 API
- ✅ r5d-3: 번들 메타 정보 API
- ✅ r5d-4: 타임라인 API severity 집계
- ✅ r5d-5: 권한 레벨 (클라이언트 사이드)

**P0 항목**: 모두 통과
**서버사이드 기준**: 만족
**코드 품질**: ESLint 0개, TypeScript 0개

---

**버전**: R5d-2 ~ R5d-5 서버사이드 구현 v1
**날짜**: 2025-01-XX
**기준선**: web-core-4.17.0(4054c04)
**P0 결함**: 해결 완료

