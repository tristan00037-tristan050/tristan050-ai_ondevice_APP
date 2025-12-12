> 이 문서는 AI 온디바이스 Enterprise OS의 **공식 개발·검토 기준 문서(v1)**입니다.  
> 투자사/임원용이 아니라, **웹(ops-console) / 앱(app-expo HUD) / 서버(BFF + 서비스 코어 + DB)** 전 구성원이  
> 모든 기능·PR·스프린트에서 따라야 하는 내부 지침서입니다.  
> 다른 문서와 충돌할 경우, 이 문서의 원칙을 우선합니다.


# AI 온디바이스 기업용 플랫폼 – Enterprise Playbook  
(웹·앱·내부 서버 공통 개발 방향 고정 문서)

---

## 0. 한 줄 요약 – 무엇을 만들고 있는가

> **"개인 PC·브라우저·사내 태블릿 위에서 돌아가는 온디바이스 AI 에이전트 + 회사 내부망에만 붙는 AI 게이트웨이(OS)"**

펫샵/소매용 서비스가 아니라,  
**국내외 일반 기업**이 내부 정보 유출 걱정 없이  
회계·CS·HR·기획·보안 업무를 자동화/보조할 수 있는 **기업용 OS 레이어**를 만든다.

이 문서는 **웹(ops-console) / 앱(app-expo HUD) / 서버(BFF + 서비스 코어 + DB)** 전 구성원이  
같은 방향을 유지하기 위한 "개발 방향 고정 지시서 + Playbook"이다.

---

## 6. 모델·지식 베이스 거버넌스

### 6-1. 모델 명명 및 버전 정책 (R10-S1 보강)

* **엔진/모델 명명 예시:**
  * `rule-v1`: 규칙 기반 엔진 v1
  * `local-llm-v0`: Stub 버전 (R9-S2 기준, 실제 모델 미연동)
  * `local-llm-v1`: 실제 온디바이스 모델 (양자화된 SLM 등)
  * `remote-llm-x`: 원격 LLM 엔진 (BFF 게이트웨이 경유)

* **코드/설정/로그 어디서든 동일한 이름 사용**
  * `local-llm-v0`는 Stub이며, 클라이언트 메모리에서만 동작하고 네트워크를 사용하지 않는다.
  * `local-llm-v1` 이후 버전은 실제 온디바이스 모델(예: 양자화된 SLM)만 사용한다.
  * 엔진 메타 정보(`EngineMeta`)에 `stub: boolean`, `variant: string` 필드로 명시한다.

* **롤백·캔어리 롤아웃을 전제로 모델 버전 설계를 한다.**

### 6-2. 모델 배포 원칙

* 새 모델/프롬프트는 항상 **도메인별 평가 세트**로 테스트 후 배포:
  * 회계 도메인: 분개 추천, 대사 결과 요약 등.
  * CS 도메인: 티켓 요약, 답변 추천 등.
* dev → pilot → prod 3단계 이상 환경을 기본 전제로 한다.

### 6-3. 지식 베이스·커넥터

* ERP/메일/Drive/티켓 시스템 등 커넥터별로:
  * 어떤 데이터가 인덱싱 대상인지,
  * 어느 테넌트/부서가 접근 가능한지,
  * 동기화 주기/보존 기간이 어떻게 되는지
  를 문서 + 설정으로 강제한다.

### 6-4. Remote LLM 모드 원칙 (R10-S1 보강)

* **Remote LLM 모드는 항상 다음 경로만 허용:**
  * `HUD/Web → BFF(LLM Gateway 모듈) → 외부 LLM`
* **HUD/Web 코드가 외부 LLM(OpenAI/Gemini 등)을 직접 HTTP 호출하는 구현은 금지한다.**
* **모든 LLM 요청(Local/Remote 불문)은 SuggestEngine 인터페이스를 통과해야 한다.**
* 게이트웨이는 다음을 담당한다:
  - 외부 LLM API 키/엔드포인트 관리
  - 요청/응답 로깅 및 마스킹
  - 테넌트/조직/권한 및 데이터 경계 정책 적용

---

## 10. 관측 데이터 및 KPI

### 10-1. 기본 메트릭 (기존)

* 회계 도메인:
  * Top-1/Top-5 정확도
  * Manual Review 비율
  * BFF Success Rate
  * HIGH Risk 거래 수

### 10-2. 관측 데이터 (R10-S1 보강)

* **CS LLM 사용 시 최소 다음 이벤트를 수집할 수 있도록 설계한다:**
  * `suggestion_shown`: 추천이 화면에 표시됨
  * `suggestion_used_as_is`: 그대로 적용됨
  * `suggestion_edited`: 수정 후 전송됨
  * `suggestion_rejected`: 무시됨

* **이 이벤트들은 원문 텍스트가 아닌 메타데이터만을 포함한다:**
  * 길이 (suggestionLength)
  * 엔진 모드 (engineMode: 'rule' | 'local-llm' | 'remote-llm')
  * 도메인 (domain: 'accounting' | 'cs')
  * 테넌트 (tenantId)
  * 사용자 (userId)
  * 역할 (userRole)
  * 타임스탬프 (timestamp)

* **원문 텍스트는 수집하지 않는다** (Playbook 4-2, 4-3 규칙 준수)

---

## 3. 사내망 게이트웨이 우선 (R10-S1 보강)

### 3-1. 기본 원칙

* 모든 외부 API 호출은 BFF(Backend-for-Frontend)를 경유한다.
* HUD/Web 클라이언트는 외부 서비스에 직접 HTTP 호출을 하지 않는다.

### 3-2. Remote LLM 게이트웨이 규칙 (R10-S1 추가)

* **Remote LLM 모드는 항상 다음 경로만 허용:**
  * `HUD/Web → BFF(LLM Gateway 모듈) → 외부 LLM`

* **HUD/Web 코드가 외부 LLM(OpenAI/Gemini 등)을 직접 HTTP 호출하는 구현은 금지한다.**

* **모든 LLM 요청(Local/Remote 불문)은 SuggestEngine 인터페이스를 통과해야 한다.**

* 게이트웨이는 다음을 담당한다:
  - 외부 LLM API 키/엔드포인트 관리
  - 요청/응답 로깅 및 마스킹
  - 테넌트/조직/권한 및 데이터 경계 정책 적용
  - Rate limiting 및 비용 관리

---

## 참고

이 문서는 R10-S1에서 다음 내용이 추가/보강되었습니다:
- 6-1: LLM 버전/엔진 명명 규칙 (stub, variant 필드 포함)
- 6-4: Remote LLM 게이트웨이 규칙 명시
- 10-2: LLM Usage KPI/Audit 예시 추가
- 3-2: Remote LLM 게이트웨이 규칙 추가

