# 운영팀 로컬 개발 환경 실행 가이드

이 문서는 운영팀이 로컬에서 웹 Backoffice와 앱 HUD 화면을 확인하기 위한 가이드입니다.

## 1. 공통 1회 세팅 (의존성 설치)

⚠️ 이미 `npm install` 완료했다면 이 블록은 생략하셔도 됩니다.

```bash
# [Cursor에 그대로 복사·붙여넣기: 초기 1회 세팅]

cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"

# 의존성 설치 (최초 1회)
npm install
```

---

## 2. 웹 Backoffice(관리 화면) 실행 명령

브라우저에서 회계 Backoffice / OS 콘솔 화면을 보고 싶을 때 사용합니다.

이 블록은 하나의 터미널(또는 Cursor Task)에서 실행하면 됩니다.

```bash
# [Cursor에 그대로 복사·붙여넣기: 웹 Backoffice 로컬 실행]

cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"

# 1) DB + BFF 서버 실행 (이미 떠 있으면 재실행되지 않습니다)
docker compose up -d db bff

# 2) Backoffice(ops-console) 개발 서버 실행
npm run dev --workspace=@appcore/ops-console
```

**사용 방법:**
- 위 명령 실행 후, 터미널 마지막 부분에 보이는 주소(예: `Local: http://localhost:5173` 또는 비슷한 형태)를 복사해서 브라우저에 입력하시면 운영팀에서 웹 화면을 직접 보실 수 있습니다.

---

## 3. 앱 HUD(모바일 화면)를 브라우저에서 실행

실제 폰 설치 없이, 브라우저에서 HUD 화면을 확인하고 싶을 때 사용합니다.

이 블록은 다른 터미널 / 다른 Cursor Task에서 돌리는 것을 권장드립니다.

```bash
# [Cursor에 그대로 복사·붙여넣기: 앱 HUD 웹 모드 실행]

cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17/packages/app-expo"

# 1) Expo 의존성 설치 (최초 1회만)
npx expo install

# 2) app-expo(모바일 HUD) 개발 서버 실행
npx expo start
```

**사용 방법:**
- 위 명령을 실행하면 터미널에 Expo 메뉴가 뜹니다.
- 키보드에서 **`w` 키를 한 번 눌러주시면**, 브라우저(보통 `http://localhost:19006` 근처)가 자동으로 열리고 HUD 화면이 보입니다.

**운영팀 안내 문구 예시:**
> 터미널에서 위 명령을 실행해 주세요.
> 
> 터미널에 Expo 메뉴가 뜨면 **`w` 키를 누르세요**.
> 
> 자동으로 열리는 브라우저 창에서 HUD 화면을 테스트하실 수 있습니다.

---

## 4. 운영팀에게 전달할 한 줄 요약 (Cursor 프롬프트용)

운영팀이 Cursor를 쓸 때는, 아래처럼 말씀만 주시면 됩니다:

### 웹 Backoffice 확인:
> "Cursor야, 아래 블록을 터미널에서 실행해 줘"
> 
> (→ 2번 블록 붙여넣기)

### 앱 HUD 화면 확인:
> "Cursor야, 다른 터미널에서 아래 블록을 실행해 줘"
> 
> (→ 3번 블록 붙여넣기, 그리고 사람이 `w` 키 입력)

---

## 참고: 운영 스크립트

로컬 환경을 빠르게 기동/점검/종료하려면 다음 npm 스크립트를 사용할 수 있습니다:

```bash
# 로컬 환경 기동 (DB + BFF)
npm run ops:local:up

# 상태 점검
npm run ops:local:status

# 종료
npm run ops:local:down
```

자세한 내용은 `scripts/ops_local_*.sh` 파일을 참고하세요.

