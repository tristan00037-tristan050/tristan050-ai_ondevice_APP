# 실행 가이드

## ⚠️ 중요: 경로에 공백이 있으므로 따옴표로 감싸야 합니다

## 1. 프로젝트 루트로 이동

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"
```

## 2. Collector 실행

```bash
# Collector 디렉토리로 이동
cd packages/collector-node-ts

# 환경 변수 설정
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET=dev-secret
export RETAIN_DAYS=30

# 의존성 설치 (처음 한 번만)
npm install

# TypeScript 빌드
npm run build

# 서버 시작
npm start
```

**예상 출력**: `Collector server running on port 9090`

## 3. Ops Console 실행 (새 터미널)

```bash
# 프로젝트 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"

# Ops Console 디렉토리로 이동
cd packages/ops-console

# 환경 변수 파일 생성
echo "VITE_COLLECTOR_URL=http://localhost:9090" > .env
echo "VITE_API_KEY=collector-key" >> .env
echo "VITE_TENANT=default" >> .env

# 의존성 설치 (처음 한 번만)
npm install

# 개발 서버 시작
npm run dev
```

**예상 출력**: `Local: http://localhost:5173/`

브라우저에서 `http://localhost:5173`을 열면 Ops Console이 표시됩니다.

## 문제 해결

### 에러: "cd: no such file or directory"

경로에 공백이 있으므로 **반드시 따옴표로 감싸야** 합니다:

```bash
# ❌ 잘못된 방법
cd /Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/...

# ✅ 올바른 방법
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/..."
```

### 에러: "package.json not found"

현재 디렉토리를 확인하세요:

```bash
pwd
```

프로젝트 루트가 아닌 경우 위의 명령어로 이동하세요.

### 한 줄로 실행 (프로젝트 루트에서)

```bash
# Collector
cd packages/collector-node-ts && export API_KEYS="default:collector-key" && export EXPORT_SIGN_SECRET=dev-secret && export RETAIN_DAYS=30 && npm install && npm run build && npm start

# Ops Console (새 터미널)
cd packages/ops-console && npm install && npm run dev
```

## 확인 사항

### Collector가 정상 실행되었는지 확인

```bash
curl http://localhost:9090/health
```

예상 응답: `{"status":"ok","service":"collector"}`

### Ops Console이 정상 실행되었는지 확인

브라우저에서 `http://localhost:5173` 접속 시 Ops Console이 표시되어야 합니다.

