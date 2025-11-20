# Phase 5.3 UI/Dashboard 구현 완료

이 문서는 Phase 5.3 UI/대시보드 구현 내용을 설명합니다.

## ✅ 구현 완료 항목

### Ops Console (웹 UI, Vite+React+TS)

**프로젝트 구조**:
- `packages/ops-console/` - Vite+React+TypeScript 프로젝트
- Tailwind CSS 스타일링
- React Router 라우팅

**주요 기능**:

1. **리포트 목록/필터/페이지네이션** (`src/pages/Reports.tsx`)
   - 리포트 목록 조회 및 표시
   - ID 기반 필터링
   - 페이지네이션 (20개씩)
   - 자동 폴링 (30초 간격)
   - ETag 캐시 활용

2. **리포트 상세 + 서명/번들 다운로드** (`src/pages/ReportDetail.tsx`)
   - 리포트 상세 정보 표시
   - 리포트 데이터 JSON 표시
   - 마크다운 표시 (있는 경우)
   - 서명 요청 및 번들 다운로드

3. **타임라인** (`src/pages/Timeline.tsx`)
   - 24/48/72/168h 시간 윈도우 선택
   - 시간 버킷별 severity 집계 표시
   - 차트 시각화
   - 자동 폴링 (60초 간격)

4. **ETag/If-None-Match 지원 클라이언트** (`src/api/client.ts`)
   - localStorage에 ETag+응답 바디 캐시
   - 304 Not Modified 수신 시 캐시 재사용
   - X-Api-Key, X-Tenant 자동 주입
   - 네트워크 오류 시 캐시 폴백

5. **Collector API 래퍼** (`src/api/reports.ts`)
   - `getReports()` - 리포트 목록
   - `getReport(id)` - 리포트 상세
   - `signReport(id)` - 리포트 서명
   - `getTimeline(windowH)` - 타임라인

6. **Severity 뱃지/테이블 컴포넌트** (`src/components/*`)
   - `SeverityBadge` - severity 뱃지 컴포넌트
   - `ReportsTable` - 리포트 테이블 컴포넌트

## 📦 환경 변수 설정

### `.env` 파일

```bash
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=collector-key
VITE_TENANT=default
```

### 프로파일별 분리

```bash
# .env.development
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=dev-key
VITE_TENANT=dev

# .env.production
VITE_COLLECTOR_URL=https://collector.example.com
VITE_API_KEY=prod-key
VITE_TENANT=prod
```

## 🚀 실행 방법

### 1. Collector 기동 (R5b 기준)

```bash
cd packages/collector-node-ts
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET=dev-secret
export RETAIN_DAYS=30
npm start
# http://localhost:9090
```

### 2. Ops Console 기동

```bash
cd packages/ops-console
cp .env.example .env
# .env 파일 수정
npm install
npm run dev
# http://localhost:5173
```

## 🧪 DoR/DoD

### DoR (Definition of Ready)

- ✅ R5b Collector 배치 코어 기준선 유지
  - 테넌트 가드, ETag, 멱등 /sign
- ✅ API Key ↔ Tenant 매핑(API_KEYS) 활성

### DoD (Definition of Done)

- ✅ 목록/상세/타임라인 3화면 제공 및 동작
- ✅ ETag/If-None-Match 루프 정상 작동
  - 변경 없을 때 304 Not Modified 수신
  - 캐시 재사용 확인
- ✅ 서명/번들 다운로드 플로우 정상
  - 토큰 포함 URL 생성
  - 번들 다운로드 동작
- ✅ 민감정보 UI 표시 금지
  - API Key는 환경변수로만 관리
  - UI에 노출하지 않음
- ✅ 린트/타입 체크 통과
  - `npm run ci` 실행

## 🔒 불변 원칙 & CI/운영 게이트

### 공통 원칙

1. **웹 코어 기준선 고정**: web-core-4.17.0(4054c04) 유지보수 모드
2. **정책/리포트 스키마 준수**: Ajv 검증(앱/Collector), CI 스키마 게이트 유지
3. **라벨 화이트리스트**: decision|ok 유지
4. **오프라인 우선**: 앱 업로더 큐(민감정보 미저장), 지수 백오프+지터
5. **테넌트 격리**: Collector 전 엔드포인트 강제 가드 + /bundle.zip 토큰 교차검증
6. **ETag 최적화**: 목록 정렬 고정/MD5 ETag 안정화, UI 304 활용
7. **OpenAPI/타입**: BFF/Collector 명세 → 타입 생성/동기화(기존 라인 유지)

### UI 특화 원칙

1. **ETag 캐시 활용**: localStorage에 ETag+응답 바디 캐시
2. **304 최적화**: 변경 없을 때 전체 응답 본문 전송하지 않음
3. **자동 폴링**: 리포트 목록 30초, 타임라인 60초 간격
4. **민감정보 보호**: API Key는 환경변수로만 관리, UI에 노출하지 않음

## 🛠 즉시 운영 체크리스트

### Collector

- [ ] `API_KEYS` 환경변수 설정
- [ ] `EXPORT_SIGN_SECRET` 설정
- [ ] `RETAIN_DAYS=30` 설정
- [ ] 운영 절차 문서화

### Ops Console

- [ ] `.env`에 `VITE_TENANT`, `VITE_API_KEY` 프로파일별 분리
- [ ] 대시보드 폴링 주기: 30~60초 권장(ETag로 최적화)
- [ ] 브라우저 캐시/ETag 동작 확인
  - 개발자 도구 Network 탭에서 304 확인
  - localStorage에 캐시 저장 확인

## 📝 다음 배치 제안

### 즉시 개발 포함

1. **필터 고도화**
   - severity 필터
   - policy_version 필터
   - 기간 프리셋(최근 24h/7d/30d)

2. **서명 감사 로그 UI**
   - `/reports/:id/sign` 호출 이력 표기
   - 요청자/iat/exp 정보 표시

3. **번들 크기/구성 카드**
   - `bundle_meta.json` 노출
   - 파일 수, 체크섬 정보 표시

4. **에러/장애 표식**
   - 최근 24h BLOCK 급증 알림
   - 임계/Δ% 설정

5. **권한 레벨**
   - 읽기 전용/다운로드 가능 권한 분리
   - 프론트 라우팅 가드

## 🧪 테스트 시나리오

### ETag 캐시 테스트

1. 리포트 목록 페이지 열기
2. 개발자 도구 Network 탭 확인
3. 첫 요청: 200 OK, ETag 헤더 확인
4. 30초 후 자동 폴링: 304 Not Modified 확인
5. localStorage에 캐시 저장 확인

### 서명/번들 다운로드 테스트

1. 리포트 상세 페이지 열기
2. "Sign & Download Bundle" 버튼 클릭
3. 서명 요청 성공 확인
4. 번들 다운로드 URL 생성 확인
5. 번들 다운로드 동작 확인

### 타임라인 테스트

1. 타임라인 페이지 열기
2. 시간 윈도우 선택 (24/48/72/168h)
3. 시간 버킷별 severity 집계 확인
4. 차트 시각화 확인
5. 자동 폴링 동작 확인

## 📌 참고사항

1. **ETag 캐시**: localStorage에 저장되므로 브라우저별로 독립적
2. **폴링 주기**: ETag로 최적화되어 네트워크 부하 최소화
3. **민감정보**: API Key는 환경변수로만 관리, UI에 노출하지 않음
4. **타입 안정성**: TypeScript로 타입 체크
5. **린트**: ESLint로 코드 품질 관리

## 🚀 배포

### 빌드

```bash
cd packages/ops-console
npm run build
```

### 프리뷰

```bash
npm run preview
```

### 프로덕션 배포

빌드된 `dist/` 디렉토리를 정적 호스팅 서비스에 배포:
- Vercel
- Netlify
- AWS S3 + CloudFront
- GitHub Pages

