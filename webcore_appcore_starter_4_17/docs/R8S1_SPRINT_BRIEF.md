# R8-S1 스프린트 개발 지시서

## 스프린트 개요

**코드네임**: R8-S1 – Second Domain & On-device Prep  
**기간**: 2주  
**목표**:
1. "두 번째 도메인"용 HUD/Backoffice 골격 추가 (회계 구조 재사용)
2. 온디바이스 LLM 탑재를 위한 엔진 계층 정리 + 테스트 강화

**두 번째 도메인**: CS(고객 문의/티켓)로 고정  
(중간에 HR/법무로 바꿔도 구조는 그대로 재사용 가능)

---

## 0. 공통 – 스프린트 전체 원칙

### 지시서 재확인
- **온디바이스 우선**: BFF는 정책·로그·연동 레이어, AI 코어 아님
- **모든 새 API는 X-Tenant / X-User-Id / X-User-Role 필수**
- **Mock / Live 플로우 반드시 쌍으로 유지**

### PR/커밋 메시지 규칙

모든 PR/커밋 설명에 아래 둘 중 하나 문장 포함:

1. **이 기능은 어떤 부서/역할(CS/회계/HR/보안)이 온디바이스로 무엇을 할 수 있게 만드는가?**
2. **이 변경은 내부 서버(게이트웨이)가 어떤 책임을 추가로 지는가?**

---

## 1. Web (ops-console) – W-08: CS 도메인 스켈레톤 + OS Dashboard 확장

### W-08-1. 메뉴/라우트 구조 확장

#### 메뉴에 CS 섹션 추가
- OS Dashboard (이미 최상단 유지)
- Accounting
- **CS (신규)**
  - `/cs/demo` – CS 티켓 데모 화면
  - `/cs/manual-review` – CS용 수동 검토 큐(스켈레톤)

#### 라우트: `/cs/demo`
- 간단한 티켓 리스트 + 상세/요약 영역
- 상단에 "Demo / Pilot Data" 배너 (회계와 동일 패턴)
- **역할**: 기업 CS팀이 "AI HUD가 우리 티켓을 어떻게 요약/분류해 줄지"를 상상해 볼 수 있는 Backoffice 뼈대

### W-08-2. OS Dashboard에 CS 카드 자리 만들기

`/os/dashboard` 하단에 "CS 모듈(준비 중)" 카드 블록 추가:
- "티켓 요약 처리 건수 (파일럿 데이터 기반)"
- "수동 검토 비율 (예정)"
- 지금은 placeholder + 0 값으로 시작해도 됨

**중요한 것은 구조**:
- `accounting_os_*_summary`와 동일한 패턴으로
- 나중에 `cs_os_*_summary` 뷰만 추가하면 바로 붙을 수 있게

---

## 2. App (app-expo / HUD) – A-08: CS HUD 스켈레톤 + 엔진 계층 정리

### A-08-1. CS HUD 스켈레톤 추가

#### 구조
- 기존 `AccountingHUD` 패턴을 복제한 `CSHUD`(가칭) 추가

#### 초기 기능
- Mock 티켓 리스트 (제목, 고객 이름, 생성 시각)
- 우측에 "AI 요약(온디바이스)" 영역
- "수동 검토 요청" 버튼 (HUD 내부 UX까지만, Live는 추후)

#### 진입 경로
- 앱 내에서 도메인 스위치 탭(Accounting / CS) 추가
- 또는 초기엔 환경변수로 CS HUD 전용 빌드만 있어도 OK

**PR 문장 예시**:
> 이 기능은 CS 상담원이 온디바이스 HUD에서 티켓 내용을 빠르게 요약/검토할 수 있게 만드는 기반입니다.

### A-08-2. SuggestEngine 계층 정리 (온디바이스 LLM 준비)

#### 현재 상태
- `SuggestEngine` 인터페이스
- `localRuleEngineV1`, `remoteEngine` 존재

#### 이번 스프린트에서 할 것

**엔진 타입 명확화**:
- `LocalRuleEngineV1` – 규칙 기반 (현 상태 유지)
- `RemoteBFEngineV1` – BFF `/postings/suggest` 기반
- **(신규 타입 정의만)** `LocalLLMEngineV1` – 온디바이스 LLM용 슬롯 (아직 Mock)

**구성 함수 개선**:
```typescript
getSuggestEngine(domain: 'accounting' | 'cs', cfg: ClientCfg)
```
- `domain = 'accounting' | 'cs'`
- Mock 모드인 경우, 기본 `LocalRuleEngineV1`
- Live 모드 + feature flag 켜져 있으면 `RemoteBFEngineV1`

**환경변수**:
- `EXPO_PUBLIC_ACCOUNTING_ENGINE=remote|local`
- `EXPO_PUBLIC_CS_ENGINE=local` (기본 온디바이스)

**UI 표시 강화**:
- HUD 상단: `Engine: On-device (Rule)` or `Engine: Remote(BFF)`
- CS HUD 카드 하단: `source: On-device (Rule)` 표시

**이 작업까지가 "R8에서 온디바이스 LLM 꽂을 자리"를 공식화하는 단계입니다.**
실제 모델 탑재는 R8-S2 이후로 넘기고, 인터페이스·플래그·표시까지만 이번에.

### A-08-3. Mock/Live 테스트 자동화(최소 1개)

**목표**: **"Mock 모드에서 네트워크 요청 0건"**을 코드 레벨에서 영구 보장.

**작업**:
- Playwright(or 기존 E2E) 시나리오 추가:
  - `npm run demo:app:mock` 기반 테스트
  - HUD 페이지 진입 후 버튼 2–3개 클릭
  - `page.route('**/*', ...)` or network log를 활용해서 실제 HTTP 요청 수가 0인지 검사
- CI에 `@p0 mock-mode-no-network` 같은 태그로 넣기

---

## 3. Server (bff-accounting / service-core / data-pg) – S-07: CS 서비스 코어 스켈레톤

**주의**: 여전히 **"기업 내부 업무 서버"가 아니라, 앱 코어에 종속된 "OS/서비스 코어"**만 다룬다.

### S-07-1. CS 도메인용 패키지/네임스페이스 뼈대

#### `@appcore/service-core-cs` (가칭) 패키지 생성

**역할**:
- 티켓 요약/분류 결과를 표현하는 타입 정의
- Risk/ManualReview에 준하는 "CS 전용 수동 검토" 도메인 스켈레톤

#### DB 스키마 (마이그)
- `010_cs_os_views.sql` (번호 예시는 맞춰서)

**최소한**:
- `cs_os_pilot_summary` – CS 파일럿 지표 요약 (row 몇 개짜리 view)

**실제 티켓/업무 데이터 테이블은 여기서 만들지 않음**
(그건 각 기업 내부 프로젝트 영역)

### S-07-2. BFF 라우트 스켈레톤 (`/v1/cs/os/dashboard`)

#### 새로운 라우트 파일
- `routes/cs-os-dashboard.ts` (가칭)

#### 엔드포인트
- `GET /v1/cs/os/dashboard`
- 파라미터: `from`, `to`, `tenant` (Accounting OS Dashboard와 동일 규칙)

#### 응답
```json
{
  "pilot": {
    "total_tickets": 0,
    "summary_count": 0,
    "manual_review_rate": 0
  }
}
```
(초기에는 전부 0/placeholder 값으로 반환)

#### 미들웨어
- `requireTenantAuth`
- `requireRole('operator','auditor')`
- OS 정책 브리지 준수

**이 라우트는 CS HUD/Backoffice가 사용할 "OS 지표 엔드포인트"일 뿐, 실제 CS 업무 서버(티켓 관리, SLA 계산 등)는 별도.**

---

## 4. 테스트 & 운영 – T-01: R7-H 라인 회귀 방지 + R8 준비

### T-01-1. Mock 모드 네트워크 0 테스트 (위에서 언급 – A-08-3)

이건 이 스프린트의 **Must-have**로 둡니다.

### T-01-2. OS Dashboard API 가드 테스트

`/v1/accounting/os/dashboard` + 신규 `/v1/cs/os/dashboard`에 대해:
- `from/to` 기간 상한(예: 30일) 넘었을 때 400 또는 clamp 되는지 테스트
- `tenant` 누락 시 정책에 맞는 4xx 또는 default tenant 동작 테스트

---

## 5. 스프린트 종료 기준 (Definition of Done)

R8-S1 스프린트가 끝났다고 인정하려면 최소 다음이 만족되어야 합니다.

### CS HUD(웹)
- [ ] `/cs/demo` 페이지에서 Mock 티켓 리스트 + 요약 영역이 보인다.
- [ ] 메뉴에 CS 영역이 OS Dashboard/Accounting와 나란히 있다.

### CS HUD(앱)
- [ ] HUD 내에서 CS 탭/버전으로 진입 가능.
- [ ] Mock 모드에서 CS HUD도 네트워크 0으로 동작.
- [ ] 상단 상태바에 `Engine: On-device (Rule)` 표시.

### SuggestEngine 계층
- [ ] 코드 상에 `LocalRuleEngineV1`, `RemoteBFEngineV1`, `LocalLLMEngineV1`(Stub) 세 타입이 정리되어 있다.
- [ ] 환경변수/설정으로 도메인별 엔진 전략을 다르게 설정 가능하다.

### BFF CS OS API
- [ ] `GET /v1/cs/os/dashboard`가 최소 placeholder JSON을 반환한다.
- [ ] OS 정책 헤더 미포함 시 4xx, 포함 시 200이 나온다.

### 테스트
- [ ] Mock 모드 네트워크 0 테스트가 CI에서 돈다.
- [ ] OS Dashboard 기간/파라미터에 대한 최소 1개 통합 테스트가 추가된다.

---

## 작업 분해 (예시 티켓)

### Web (W-08)
- [ ] W-08-1: 메뉴/라우트 구조 확장 (CS 섹션 추가)
- [ ] W-08-2: OS Dashboard에 CS 카드 자리 만들기

### App (A-08)
- [ ] A-08-1: CS HUD 스켈레톤 추가
- [ ] A-08-2: SuggestEngine 계층 정리 (LocalLLMEngineV1 Stub 추가)
- [ ] A-08-3: Mock/Live 테스트 자동화

### Server (S-07)
- [ ] S-07-1: CS 도메인용 패키지/네임스페이스 뼈대
- [ ] S-07-2: BFF 라우트 스켈레톤 (`/v1/cs/os/dashboard`)

### Test (T-01)
- [ ] T-01-1: Mock 모드 네트워크 0 테스트
- [ ] T-01-2: OS Dashboard API 가드 테스트

---

## 중요 원칙 재확인

이 지시서를 기준으로 하면,

- 지금까지 만든 **"회계 + OS/HUD 코어"를 건드리지 않고**
- 두 번째 도메인(CS)와 **"온디바이스 LLM 자리"까지 준비**하면서
- 여전히 **"앱 코어 + OS 게이트웨이" 범위 안에 머무르게** 됩니다.

---

## 참고 문서

- [R7-H+4 개발 브리핑](./R7H_PLUS4_DEV_BRIEF.md)
- [R8 준비 문서](./R8_PREPARATION.md)
- [POC Playbook](./POC_PLAYBOOK.md)

