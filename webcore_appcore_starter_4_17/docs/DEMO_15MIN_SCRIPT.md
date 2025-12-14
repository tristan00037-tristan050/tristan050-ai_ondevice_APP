# 고객 데모용 15분 시나리오

## 개요

이 문서는 외부 고객/파트너에게 AI 온디바이스 회계 OS를 시연할 때 사용하는 스크립트입니다. 약 15분 분량으로, 제품의 핵심 가치를 단계별로 보여줍니다.

---

## 오프닝 (1분)

> "이 제품은 사내 PC·브라우저에서 돌아가는 온디바이스 회계 HUD와
> 그 뒤에서 정책·로그·연동을 담당하는 기업용 OS 게이트웨이입니다.
> 
> 오늘은 '하루 동안 회계팀에서 무슨 일이 일어났는지' 관점으로 보여드리겠습니다."

---

## Step 1 – OS Dashboard (상황판) 🔍 (3–4분)

### 준비
```bash
npm run demo:web
# → http://localhost:5173/os/dashboard 열어놓기
```

### 시연 포인트

#### 1. 상단 카드 설명

**"지난 24시간 Top-1 정확도"**
- AI 추천 중 1순위가 실제 선택과 일치한 비율
- 툴팁: "Top-1: AI 추천 중 1순위가 실제 선택과 일치한 비율입니다."

**"지난 24시간 수동 검토 비율"**
- 전체 추천 중 수동 검토로 넘어간 비율
- 툴팁: "전체 추천 중 수동 검토로 넘어간 비율입니다."

**"지난 24시간 HIGH Risk 거래 수"**
- 최근 24시간 동안 발생한 HIGH Risk 거래 수
- 툴팁: "최근 24시간 동안 발생한 HIGH Risk 거래 수입니다."

**"Manual Review 대기 건 수"**
- 현재 수동 검토 대기 중인 건 수
- 툴팁: "현재 수동 검토 대기 중인 건 수입니다."

**"최근 5분간 BFF 성공률 / P95 지연 시간"**
- BFF API 호출 중 성공한 비율
- 툴팁: "BFF API 호출 중 성공한 비율입니다."

**"엔진 모드" (R8-S2 신규)**
- 현재 주요 엔진 모드 (On-device LLM / 규칙 기반 / Mock 등)
- 지난 24시간 기준 엔진 사용 분포
- 툴팁: "지난 24시간 기준 엔진 사용 분포와 주요 엔진 모드입니다."

#### 2. Demo 배너 설명

> "지금은 데모/파일럿 데이터 기준이고, 실제 도입 시에는 귀사 ERP/회계 데이터로 그대로 들어옵니다."

#### 3. 하단 Demo Flow 블록 설명

**① 회계 데모** → HUD에서 어떻게 보이는지
- 클릭하여 `/demo/accounting` 이동

**② 수동 검토 Workbench** → 사람이 어떻게 개입하는지
- 클릭하여 `/manual-review` 이동

**③ Risk Monitor** → 리스크 관점을 어떻게 묶어보는지
- Risk 섹션/페이지로 이동

### 핵심 메시지

> **"경영진/운영팀은 이 화면 하나로 'AI 회계 HUD가 제대로 일하고 있는지'를 봅니다."**

---

## Step 2 – HUD Mock 모드 (온디바이스 메시지) 💻 (4–5분)

### 목표
**"네트워크 없어도 UX/업무동선 테스트 가능" 보여주기**

### 준비
```bash
npm run demo:app:mock
# → Expo 메뉴에서 'w' 키 입력하여 브라우저 열기
```

### 시연 포인트

#### 1. 상단 상태바 확인
- **Mode: Mock**
- **Engine: Mock** 또는 **Engine: Rule** 표시 확인
- **"Mock 모드에서는 항상 로컬 규칙 엔진을 사용합니다"** 설명

#### 2. Chrome DevTools → Network 탭 열어놓기

#### 3. HUD에서 작업 수행
1. 설명 입력 → "추천" 버튼 클릭
2. 승인/수동 검토 버튼 여러 번 클릭

#### 4. **체크포인트: HTTP 요청이 0건인 것을 손가락으로 짚어주기**
- Network 탭에서 HTTP 요청이 하나도 없음을 확인
- **"Mock 모드에서는 네트워크 호출이 전혀 발생하지 않습니다"** 강조

#### 5. HIGH Risk 카드가 나왔을 때
- **"⚠ 고위험 거래 – 수동 검토 권장"** 문구 확인
- **"수동 검토 요청"** 버튼 클릭
- Alert: **"수동 검토 요청이 접수되었습니다. (모의)"**
- 콘솔: `[MOCK] ManualReviewButton ...` 로그 확인

#### 6. QueueInspector 열기
- "전송 대기 항목 보기" 버튼 클릭
- 로컬에 쌓인 오프라인 큐 항목/카운트 보여주기
- Mock 모드에서는 실제 전송 없이 로컬에만 저장됨을 설명

### 핵심 메시지

> **"이 HUD는 기본적으로 온디바이스 앱입니다.
> 실제 서버랑 안 붙여도, 회사 내부 UX/업무 플로우를 먼저 검증할 수 있습니다."**

---

## Step 3 – HUD Live 모드 + Risk + Manual Review 🔄 (5–6분)

### 목표
**"실제 BFF + DB랑 붙었을 때 한 사이클" 보여주기**

### 준비

#### 서버 쪽
```bash
export DATABASE_URL="postgres://app:app@localhost:5432/app"
npm run db:migrate
docker compose up -d --build bff db
npm run demo:seed   # 필요 시
```

#### HUD Live 기동
```bash
npm run demo:app:live
```

### 시연 포인트

#### 1. HUD 상단 확인
- **Mode: Live(BFF)**
- **Engine: Rule** 또는 **Engine: On-device LLM** 표시 확인
- **"Live 모드에서는 엔진 모드에 따라 다른 추론 경로를 사용합니다"** 설명

#### 2. 데모 플로우

**100만 원 이상 거래를 입력 → Suggest**
- 예: "스타벅스 커피 1,500,000원"

**HIGH Risk 뱃지가 뜨는 항목 선택**
- 붉은 Risk Badge 확인
- **"⚠ 고위험 – 수동 검토 추천"** 문구 확인

**"수동 검토 요청" 클릭**
- 성공 메시지(Alert/Toast): "수동 검토 큐에 추가되었습니다."
- Offline Queue에 잠깐 쌓였다가 전송되는 모습 확인

#### 3. (선택) 네트워크 끊기 데모
- 네트워크를 일부러 끊어서 Offline Queue 한두 건 만들어 보여주기
- 네트워크 복구 후 자동 전송되는 모습 확인

#### 4. **엔진 모드 전환 데모 (R8-S2 신규)**
- **Step X: HUD 상단 상태바에서 Engine 모드 확인**
  - 현재 `Engine: Rule` 또는 `Engine: On-device LLM` 표시 확인
  - **"지금은 Rule 엔진을 사용하고 있습니다"** 설명

- **Step Y: 동일 시나리오를 ENGINE_MODE=local-llm로 다시 실행**
  ```bash
  # 터미널에서 HUD 재시작
  EXPO_PUBLIC_ENGINE_MODE=local-llm npm run demo:app:live
  ```
  - HUD 상단 상태바에서 `Engine: On-device LLM` 표시 확인
  - 동일한 입력으로 추천 요청 → **"이제 온디바이스 LLM 엔진이 추론합니다"** 설명
  - (선택) OS Dashboard에서 Engine Mode 카드 확인
    - `primary_mode: local-llm` 및 `counts` 분포 확인

<
### 핵심 메시지

> **"고위험 거래는 자동으로 리스크 스코어링 되고,
> 사람이 봐야 할 건 Manual Review Queue로 자동 올라갑니다.
> 그리고 엔진 모드를 전환하여 온디바이스 LLM 추론도 사용할 수 있습니다."**

---

## Step 4 – Manual Review Workbench (Backoffice) 📋 (3–4분)

### 준비
웹 브라우저에서 `/manual-review` 접속

### 시연 포인트

#### 1. 상단 요약 카드
- **대기** / **검토 중** / **오늘 처리 건수** 확인
- 방금 HUD에서 보낸 수동 검토 건이 **PENDING**으로 떠 있는지 보여주기

#### 2. 테이블에서 해당 건 클릭
- 생성 시각
- Posting ID
- Risk Level: **HIGH**
- 이유: `["HIGH_VALUE"]`
- 요청자
- 상태: **PENDING**

#### 3. 상태 변경
- **auditor** 역할이면 **승인/거절** 버튼 클릭
- 상태가 **APPROVED** 또는 **REJECTED**로 바뀌는 걸 보여줌
- Note 필드에 코멘트 입력 가능

### 핵심 메시지

> **"AI가 자동 추천은 하지만, 최종 결정은 여전히 담당자가 합니다.
> 그리고 그 전 과정이 감사 가능하게 남는다는 게 OS 관점의 포인트입니다."**

---

## 마무리 (1분)

### 요약
1. **OS Dashboard**: 경영진/운영팀이 한 화면에서 전체 상황 파악
2. **HUD Mock 모드**: 네트워크 없이도 UX/업무 플로우 검증 가능
3. **HUD Live 모드**: 실제 BFF + DB 연동으로 자동화된 리스크 관리
4. **Manual Review Workbench**: 사람의 최종 결정 + 감사 추적

### 다음 단계
- 파일럿 환경 구축
- 실제 ERP/회계 시스템 연동
- 온디바이스 LLM 통합 (R8)

---

## FAQ (예상 질문)

### Q1. "온디바이스"라는 게 정확히 뭘 의미하나요?
**A**: 네트워크 없이도 HUD가 동작하고, AI 추천을 로컬에서 생성할 수 있다는 의미입니다. 실제 서버와 연결되면 더 정확한 추천과 감사 추적이 가능합니다.

### Q2. Mock 모드와 Live 모드의 차이는?
**A**: 
- **Mock**: 네트워크 호출 없음, 온디바이스 규칙 엔진 사용, 로컬 저장소만 사용
- **Live**: BFF 서버와 통신, 원격 AI 엔진 사용, DB에 모든 이벤트 저장

### Q3. Risk Score는 어떻게 계산되나요?
**A**: 현재는 규칙 기반입니다 (금액 > 100만 원 = HIGH, 50-100만 원 = MEDIUM). R8-S2에서 온디바이스 LLM 엔진 모드를 도입했으며, 실제 LLM 모델 연동은 다음 스프린트에서 진행 예정입니다.

### Q4. 엔진 모드는 어떻게 전환하나요?
**A**: `EXPO_PUBLIC_ENGINE_MODE` 환경 변수로 선택할 수 있습니다 (`rule`, `local-llm`, `mock`, `remote`). 현재는 환경 변수 변경 후 HUD 재시작이 필요합니다.

### Q5. Manual Review는 누가 처리하나요?
**A**: `auditor` 권한을 가진 담당자가 Backoffice에서 승인/거절합니다. 모든 과정이 감사 로그로 남습니다.

---

## 체크리스트 (시연 전)

- [ ] DB 마이그레이션 완료 (`npm run db:migrate`)
- [ ] BFF 서버 실행 중 (`docker compose up -d bff`)
- [ ] 웹 서버 실행 중 (`npm run demo:web`)
- [ ] HUD Mock 모드 테스트 (Network 탭 0건 확인)
- [ ] HUD Live 모드 테스트 (BFF 연결 확인)
- [ ] Manual Review 샘플 데이터 생성 (`npm run demo:seed`)
- [ ] Chrome DevTools Network 탭 열어놓기
- [ ] 브라우저 콘솔 열어놓기 (Mock 모드 로그 확인용)


