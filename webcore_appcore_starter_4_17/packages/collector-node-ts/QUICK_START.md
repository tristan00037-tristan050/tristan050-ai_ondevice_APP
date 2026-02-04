# Collector 서버 빠른 시작 가이드

## 서버 시작

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17/packages/collector-node-ts"

# 환경 변수 설정
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET=dev-secret
export RETAIN_DAYS=30

# 빌드 (변경사항이 있을 경우)
npm run build

# 서버 시작
npm start
```

## 서버 종료

```bash
# 방법 1: 터미널에서 Ctrl+C

# 방법 2: 프로세스 종료
pkill -f "node dist/index.js"

# 방법 3: 포트를 사용하는 프로세스 찾아서 종료
lsof -i :9090  # PID 확인
kill -9 <PID>  # PID로 종료
```

## 사용 가능한 엔드포인트

### 인증 불필요
- `GET /` - API 정보 및 엔드포인트 목록
- `GET /health` - Health check

### 인증 필요 (X-Api-Key, X-Tenant 헤더)
- `GET /reports` - 리포트 목록 조회
- `GET /reports/:id` - 리포트 상세 조회
- `POST /reports/:id/sign` - 리포트 서명 요청
- `GET /reports/:id/bundle.zip?token=...` - 리포트 번들 다운로드
- `GET /timeline?window_h=24` - 타임라인 조회
- `POST /ingest/qc` - 리포트 인제스트
- `POST /admin/retention/run` - 보존 정책 실행

## 테스트

```bash
# Health check
curl http://localhost:9090/health

# API 정보
curl http://localhost:9090/

# 리포트 목록 (인증 필요)
curl -H "X-Api-Key: collector-key" -H "X-Tenant: default" http://localhost:9090/reports
```

## 문제 해결

### 포트가 이미 사용 중인 경우
```bash
# 포트 9090을 사용하는 프로세스 확인
lsof -i :9090

# 프로세스 종료
kill -9 <PID>
```

### 모듈을 찾을 수 없는 경우
```bash
# 의존성 재설치
npm install

# 재빌드
npm run build
```

