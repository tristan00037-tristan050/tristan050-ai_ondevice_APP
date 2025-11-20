# Ops Console

Collector 서버의 리포트를 조회하고 관리하는 웹 UI입니다.

## 사전 요구사항

1. Collector 서버가 실행 중이어야 합니다 (`http://localhost:9090`)
2. Node.js 18+ 및 npm이 설치되어 있어야 합니다

## 설치

```bash
cd packages/ops-console
npm install
```

## 환경 변수 설정

`.env` 파일을 생성하고 다음 내용을 추가하세요:

```bash
VITE_COLLECTOR_URL=http://localhost:9090
VITE_API_KEY=collector-key
VITE_TENANT=default
```

또는 한 번에 생성:

```bash
echo "VITE_COLLECTOR_URL=http://localhost:9090" > .env
echo "VITE_API_KEY=collector-key" >> .env
echo "VITE_TENANT=default" >> .env
```

## 개발 서버 실행

```bash
npm run dev
```

브라우저에서 `http://localhost:5173` 접속

## 빌드

```bash
npm run build
```

빌드 결과는 `dist/` 디렉토리에 생성됩니다.

## 미리보기

```bash
npm run preview
```

## 린트 및 타입 체크

```bash
# 린트
npm run lint

# 타입 체크
npm run type-check

# 모두 실행 (CI)
npm run ci
```

## 문제 해결

### `vite: command not found`

의존성을 설치하세요:

```bash
npm install
```

### Collector 서버에 연결할 수 없음

1. Collector 서버가 실행 중인지 확인:
   ```bash
   curl http://localhost:9090/health
   ```

2. `.env` 파일의 `VITE_COLLECTOR_URL`이 올바른지 확인

### 포트 5173이 이미 사용 중

Vite는 자동으로 다른 포트를 사용하거나, `vite.config.ts`에서 포트를 변경할 수 있습니다.
