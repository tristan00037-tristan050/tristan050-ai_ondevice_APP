# ALGO-CORE Gateway PC 배포 가이드 (초등학생도 따라하는 버전)

목표
- 게이트웨이 PC 1대에서 bff-accounting을 "항상 켜두기"
- prod 서명키가 없으면 서비스가 시작되지 않게 하기(fail-closed)
- /v1/os/algo/three-blocks 호출이 ok=true로 성공하는지 확인하기

절대 금지(중요)
- ALGO_CORE_SIGN_PRIVATE_KEY_B64(비밀키)는 채팅/슬랙/PR/이슈/로그에 붙여넣지 않는다.
- env 파일(/etc/bff-accounting.env)에 키를 넣었다면, Git에 커밋하지 않는다.

---

## 1. 게이트웨이 PC 준비

1) PC에 접속(SSH)
2) 레포가 있는지 확인
- 없다면 레포를 내려받는다.

예시(레포 위치를 /opt/bff/app 으로 두는 경우):
- /opt/bff/app 안에 이 레포가 있어야 한다.

---

## 2. env 파일 만들기 (키 주입)

게이트웨이 PC에서 아래 파일을 만든다.

파일 경로:
- /etc/bff-accounting.env

내용은 반드시 "줄바꿈 5줄"이어야 한다.

```env
ALGO_CORE_MODE=prod
ALGO_CORE_SIGN_PUBLIC_KEY_B64=...
ALGO_CORE_SIGN_PRIVATE_KEY_B64=...
ALGO_CORE_SIGNING_KEY_ID=...
ALGO_CORE_ALLOWED_SIGNING_KEY_IDS=...
PORT=8081
```

권한 잠금(필수):
```bash
chmod 600 /etc/bff-accounting.env
```

## 3. 서비스 빌드

레포 폴더로 이동:
```bash
cd webcore_appcore_starter_4_17/packages/bff-accounting
```

그 다음:
```bash
npm install
npm run build
```

## 4. systemd로 "자동 실행" 설정

서비스 파일 생성:
- /etc/systemd/system/bff-accounting.service

예시:
```ini
[Unit]
Description=bff-accounting (ALGO-CORE gateway)
After=network.target

[Service]
Type=simple
User=bff
WorkingDirectory=/opt/bff/app/webcore_appcore_starter_4_17/packages/bff-accounting
EnvironmentFile=/etc/bff-accounting.env
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

적용/실행:
```bash
systemctl daemon-reload
systemctl enable bff-accounting
systemctl restart bff-accounting
systemctl status bff-accounting
```

성공 기준:
- status가 `active (running)`

## 5. 정상 동작 확인(중요)

### 5-1) 서버가 살아있는지 확인(헬스체크)
```bash
curl -sS "http://127.0.0.1:8081/healthz" || true
```

### 5-2) ALGO-CORE 엔드포인트 호출

아래 호출은 "인증 헤더"가 환경에 따라 다를 수 있다.

먼저 A(최소 헤더)로 호출
- 401/403이 나오면 B(추가 헤더)로 다시 호출

**A) 최소 헤더**
```bash
curl -sS -D /tmp/algo_hdr.txt -o /tmp/algo_body.json \
  -X POST "http://127.0.0.1:8081/v1/os/algo/three-blocks" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: dev-key:operator" \
  -H "X-Tenant: default" \
  --data '{"request_id":"gw_prod_check","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"algo-core-prod","device_class":"web","client_version":"prod","constraints":{"language":"ko","max_tokens":128},"ts_utc":"2026-01-28T00:00:00Z"}'
```

**B) 추가 헤더(환경에서 요구하는 경우)**
```bash
curl -sS -D /tmp/algo_hdr.txt -o /tmp/algo_body.json \
  -X POST "http://127.0.0.1:8081/v1/os/algo/three-blocks" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: dev-key:operator" \
  -H "X-Tenant: default" \
  -H "X-User-Id: test-user" \
  -H "X-User-Role: operator" \
  --data '{"request_id":"gw_prod_check","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"algo-core-prod","device_class":"web","client_version":"prod","constraints":{"language":"ko","max_tokens":128},"ts_utc":"2026-01-28T00:00:00Z"}'
```

성공 기준(바디):
- /tmp/algo_body.json 안에 `ok=true`
- `blocks`가 3개
- `manifest.sha256` 존재
- `signature.b64` / `signature.public_key_b64` 존재
- `signature.mode=prod`

헤더 확인(중요):
- `X-OS-Algo-Manifest-SHA256`가 있어야 한다.
- `X-OS-Algo-Latency-Ms`가 있으면 더 좋다.

```bash
grep -i "^X-OS-Algo-" /tmp/algo_hdr.txt || true
cat /tmp/algo_body.json
```

## 6. Fail-Closed 확인(의도된 즉시 종료)

목표:
- 키가 없거나 잘못되면 서비스가 "시작되지 않아야" 정상

방법(예시):
- /etc/bff-accounting.env에서 `ALGO_CORE_SIGN_PRIVATE_KEY_B64`를 비운다.
- `systemctl restart bff-accounting`
- status 또는 로그에서 즉시 종료 및 에러 메시지를 확인한다.

로그 확인:
```bash
sudo journalctl -u bff-accounting -n 200 --no-pager
```

기대:
- `ALGO_CORE_PROD_KEYS_REQUIRED_FAILCLOSED` 같은 에러가 보이고, 서비스는 running 상태가 아니어야 한다.

## 7. 문제 해결(서버가 안 뜰 때)

### 상태 확인
```bash
systemctl status bff-accounting
```

### 최근 로그 200줄
```bash
journalctl -u bff-accounting -n 200 --no-pager
```

### env 파일 존재/권한 확인(값은 출력하지 않는다)
```bash
ls -l /etc/bff-accounting.env
cut -d= -f1 /etc/bff-accounting.env
```

### 서비스 관리 명령
- 재시작: `systemctl restart bff-accounting`
- 중지: `systemctl stop bff-accounting`
- 자동실행 해제: `systemctl disable bff-accounting`
