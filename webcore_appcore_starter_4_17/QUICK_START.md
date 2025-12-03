# 빠른 시작 가이드

## 현재 디렉토리 확인

```bash
# 프로젝트 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"
```

## 1. Collector 기동

```bash
# Collector 디렉토리로 이동
cd packages/collector-node-ts

# 환경 변수 설정
export API_KEYS="default:collector-key"
export EXPORT_SIGN_SECRET=dev-secret
export RETAIN_DAYS=30

# 의존성 설치 (처음 한 번만)
npm install

# 빌드
npm run build

# 서버 시작
npm start
```

서버가 `http://localhost:9090`에서 실행됩니다.

## 2. Ops Console 기동

새 터미널 창에서:

```bash
# 프로젝트 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"

# Ops Console 디렉토리로 이동
cd packages/ops-console

# 환경 변수 파일 생성
cat > .env << EOF
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=collector-key
VITE_TENANT=default
EOF

# 의존성 설치 (처음 한 번만)
npm install

# 개발 서버 시작
npm run dev
```

브라우저에서 `http://localhost:5173`을 열면 Ops Console이 표시됩니다.

## 3. BFF 기동 (선택사항)

새 터미널 창에서:

```bash
# 프로젝트 루트로 이동
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"

# BFF 디렉토리로 이동
cd packages/bff-node-ts

# 의존성 설치 및 빌드
npm install
npm run build

# 서버 시작
npm start
```

## 문제 해결

### "package.json not found" 에러

현재 디렉토리를 확인하세요:

```bash
pwd
```

프로젝트 루트가 아닌 경우:

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"
```

### 경로에 공백이 있는 경우

경로에 공백이 있으므로 따옴표로 감싸야 합니다:

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"
```

### 상대 경로 사용

프로젝트 루트에서:

```bash
# Collector
cd packages/collector-node-ts
npm install && npm run build && npm start

# Ops Console (새 터미널)
cd packages/ops-console
npm install && npm run dev
```


