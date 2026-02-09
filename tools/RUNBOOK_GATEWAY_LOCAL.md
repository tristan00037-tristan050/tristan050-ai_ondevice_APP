# Gateway 로컬 실행 가이드

## 빠른 시작

터미널에서 아래 1줄만 실행하세요:

```bash
bash tools/run_gateway_local.sh
```

서버가 시작되면 `http://127.0.0.1:8081`에서 Gateway가 실행됩니다.

## 서버 상태 확인

### Healthz 확인

```bash
curl -i http://127.0.0.1:8081/healthz
```

정상 응답 예시:
```
HTTP/1.1 200 OK
...
2e8e5564049b690679336ae452b4ef7016907dd4
```

### 서버 프로세스 확인

```bash
ps aux | grep "bff-accounting"
```

또는 PID 파일 확인:
```bash
cat /tmp/gateway_local.pid
```

## 서버 종료

```bash
kill $(cat /tmp/gateway_local.pid)
```

또는 프로세스 직접 종료:
```bash
lsof -ti:8081 | xargs kill
```

## 흔한 실패 원인

### 1. 빌드 실패

**증상:**
- 스크립트 실행 중 "빌드 실패" 메시지
- `dist/index.js` 파일이 생성되지 않음

**확인 방법:**
```bash
cd webcore_appcore_starter_4_17/packages/bff-accounting
npm run build
```

**해결:**
- TypeScript 에러 확인 및 수정
- `npm install` 재실행

### 2. 데이터베이스 연결 실패

**증상:**
- 서버가 시작되지만 healthz가 응답하지 않음
- 로그에 "ECONNREFUSED" 또는 "DATABASE" 관련 에러

**확인 방법:**
```bash
tail -f /tmp/gateway_local.log
```

**해결:**
- PostgreSQL이 실행 중인지 확인:
  ```bash
  ps aux | grep postgres
  ```
- DATABASE_URL 환경 변수 확인:
  ```bash
  echo $DATABASE_URL
  ```
- 기본값: `postgres://app:app@127.0.0.1:5432/app`

## 로그 확인

### 실시간 로그 보기

```bash
tail -f /tmp/gateway_local.log
```

### 마지막 50줄 보기

```bash
tail -n 50 /tmp/gateway_local.log
```

## 스크립트 동작 방식

1. **레포 루트 찾기**: git 명령어로 레포 루트 자동 탐지
2. **디렉터리 확인**: `webcore_appcore_starter_4_17/packages/bff-accounting` 존재 확인
3. **포트 점검**: 8081 포트 사용 중인 프로세스 확인 및 종료 (bff-accounting만)
4. **의존성 설치**: `npm install` (node_modules 없을 때만)
5. **빌드**: `npm run build`
6. **서버 시작**: `PORT=8081 npm start` (백그라운드)
7. **Healthz 폴링**: 최대 30초간 1초 간격으로 확인

## 환경 변수

스크립트 실행 전에 설정 가능:

```bash
export USE_PG=1
export DATABASE_URL="postgres://app:app@127.0.0.1:5432/app"
export EXPORT_SIGN_SECRET="dev-export-secret"
bash tools/run_gateway_local.sh
```

## 주의사항

- **npm workspaces 사용 안 함**: 이 스크립트는 `bff-accounting` 패키지를 직접 실행합니다.
- **포트 충돌**: 다른 프로세스가 8081 포트를 사용 중이면 수동으로 확인 후 종료해야 합니다.
- **Windows 미지원**: Mac/Linux 전용입니다. Windows에서는 WSL 또는 Git Bash 사용을 권장합니다.

## Launcher 실행

### 웹서버 시작
```bash
cd tools/launcher_p0
python3 -m http.server 5179
```

### 브라우저 접속
```
http://127.0.0.1:5179
```

