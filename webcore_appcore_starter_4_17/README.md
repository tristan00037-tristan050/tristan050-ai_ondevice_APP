# App Core Monorepo R5c (Phase 5.3 UI/Dashboard)

R5b 배치 코어 기준선에 Phase 5.3 UI/대시보드를 추가한 완성 번들입니다.

## 📦 포함 내용

### 1. 앱 코어 (Expo RN)
- `packages/app-expo/` - React Native 앱
- Ajv 풀 스키마 검증
- 업로더 (지수 백오프+지터, 큐 보안, NetInfo 가드)
- HUD 컴포넌트

### 2. Collector (수집기)
- `packages/collector-node-ts/` - Node.js 서버
- 테넌트/권한 가드 강제
- ETag/If-None-Match 지원
- 멱등 서명
- 타임라인 API

### 3. BFF
- `packages/bff-node-ts/` - Backend for Frontend
- 정책/관측 엔드포인트

### 4. Ops Console (웹 UI)
- `packages/ops-console/` - Vite+React+TypeScript
- 리포트 목록/필터/페이지네이션
- 리포트 상세 + 서명/번들 다운로드
- 타임라인 (24/48/72/168h)
- ETag/If-None-Match 지원 클라이언트

## 🚀 빠른 실행

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

### 2. BFF 기동

```bash
cd packages/bff-node-ts
npm install
npm run build
npm start
# http://localhost:8080
```

### 3. Ops Console 기동

```bash
cd packages/ops-console
npm install
cp env.example .env
# .env 파일 수정:
# VITE_COLLECTOR_URL=http://localhost:9090
# VITE_API_KEY=collector-key
# VITE_TENANT=default
npm run dev
# http://localhost:5173
```

### 4. App (Expo)

```bash
cd packages/app-expo
npm install
npx expo install
npm run start
```

## 🧪 CI/운영 게이트

### 루트에서 실행

```bash
npm install
npm run ci
```

CI 검증 항목:
- ESLint (모든 패키지)
- TypeScript 타입 체크
- Ajv 스키마 검증
- 레드랙션 커버리지 측정
- OpenAPI 타입 생성/동기화

## 📝 환경 변수

### Collector

```bash
API_KEYS="default:collector-key,teamA:teamA-key"
EXPORT_SIGN_SECRET=<read-from-local-secret-store>
RETAIN_DAYS=30
```

### Ops Console

```bash
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=collector-key
VITE_TENANT=default
```

## 🔒 불변 원칙

1. **웹 코어 기준선 고정**: web-core-4.17.0(4054c04) 유지보수 모드
2. **정책/리포트 스키마 준수**: Ajv 검증(앱/Collector), CI 스키마 게이트 유지
3. **라벨 화이트리스트**: decision|ok 유지
4. **오프라인 우선**: 앱 업로더 큐(민감정보 미저장), 지수 백오프+지터
5. **테넌트 격리**: Collector 전 엔드포인트 강제 가드 + /bundle.zip 토큰 교차검증
6. **ETag 최적화**: 목록 정렬 고정/MD5 ETag 안정화, UI 304 활용
7. **OpenAPI/타입**: BFF/Collector 명세 → 타입 생성/동기화

## 📚 문서

- `docs/PHASE_5_3_UI.md` - UI DoR/DoD, 운영 체크리스트
- `docs/R5B_FIXES.md` - R5b P0/P1 보완 사항
- `docs/PHASE_5_3_BATCH.md` - Phase 5.3 배치 작업
- `docs/SPRINT_TASKS.md` - 스프린트 태스크

## 🛠 다음 배치 제안

1. 필터 고도화 (severity, policy_version, 기간 프리셋)
2. 서명 감사 로그 UI
3. 번들 크기/구성 카드
4. 에러/장애 표식 (BLOCK 급증 알림)
5. 권한 레벨 (읽기 전용/다운로드 가능 권한 분리)
