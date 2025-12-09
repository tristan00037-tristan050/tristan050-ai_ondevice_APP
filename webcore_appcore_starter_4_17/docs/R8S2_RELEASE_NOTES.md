# R8-S2 Release Notes

## 개요

R8-S2 릴리스는 **온디바이스 LLM 엔진 모드**를 도입하고, OS Dashboard에 엔진 모니터링 기능을 추가한 스프린트입니다. 이번 릴리스로 Accounting HUD에서 온디바이스 LLM 추론 경로를 사용할 수 있게 되었으며, 운영팀은 OS Dashboard에서 엔진 모드 사용 현황을 실시간으로 모니터링할 수 있습니다.

## 주요 기능

### 1. Engine Mode 시스템 (App)

#### EngineMode 타입 정의
- **엔진 모드**: `'mock' | 'rule' | 'local-llm' | 'remote'` 4가지 모드 지원
- **환경 변수**: `EXPO_PUBLIC_ENGINE_MODE`로 엔진 모드 선택
- **Demo 모드 우선**: `EXPO_PUBLIC_DEMO_MODE=mock`일 때는 항상 mock/rule 엔진 사용

#### LocalLLMEngineV1 구현
- **온디바이스 LLM 엔진 어댑터**: `OnDeviceLLMAdapter` 인터페이스 기반
- **DummyLLMAdapter**: 로딩/추론 지연 시뮬레이션 (실제 LLM 라이브러리 연동 준비)
- **Fallback 메커니즘**: LLM 추론 실패 시 규칙 기반 엔진으로 자동 전환
- **초기화 로직**: `initialize()` 메서드로 엔진 준비 상태 관리

#### AccountingHUD 통합
- **엔진 상태 표시**: 상단 상태바에 현재 엔진 모드 표시
  - `Engine: On-device LLM` (local-llm 모드)
  - `Engine: Rule` (rule 모드)
  - `Engine: Mock` (mock 모드)
  - `Engine: Loading...` (초기화 중)
  - `Engine: Error` (오류 발생 시)
- **자동 초기화**: 엔진이 준비되지 않았을 때 자동으로 초기화 수행
- **에러 처리**: 엔진 오류 시 사용자에게 명확한 피드백 제공

### 2. Engine Mode Tracking (Server)

#### Audit 이벤트에 engine_mode 기록
- **X-Engine-Mode 헤더**: HUD에서 BFF로 요청 시 엔진 모드 전달
- **Audit 로그**: `postings_suggest` 이벤트의 `payload.engine_mode` 필드에 기록
- **헤더 검증**: 허용된 엔진 모드만 기록 (mock, rule, local-llm, remote)

#### OS Dashboard Engine 섹션
- **DB View**: `accounting_os_engine_summary` 뷰 생성
  - 지난 24시간 기준 테넌트별, 엔진 모드별 집계
  - `postings_suggest` 이벤트에서 `engine_mode` 추출
- **API 응답**: `/v1/accounting/os/dashboard`에 `engine` 섹션 추가
  ```json
  {
    "engine": {
      "primary_mode": "local-llm",
      "counts": {
        "mock": 0,
        "rule": 12,
        "local-llm": 34,
        "remote": 0
      }
    }
  }
  ```
- **Primary Mode**: 가장 많이 사용된 엔진 모드 자동 계산

### 3. Engine Mode Card (Web)

#### OS Dashboard 카드 추가
- **Engine Mode 카드**: OS Dashboard에 새로운 요약 카드 추가
- **주요 엔진 표시**: `primary_mode`를 자연어로 표시
  - `On-device LLM` (local-llm)
  - `규칙 기반` (rule)
  - `Mock (데모)` (mock)
  - `원격 LLM` (remote)
- **사용 분포**: 지난 24시간 기준 엔진 모드별 사용 횟수 표시
- **Demo 모드 안내**: Demo 환경에서 적절한 안내 문구 표시

### 4. 테스트 강화

#### App 엔진 모드 테스트
- **모드 조합 검증**: `DEMO_MODE` × `ENGINE_MODE` 조합별 동작 검증
  - `DEMO_MODE=mock`: 항상 mock/rule 엔진 사용
  - `DEMO_MODE=live, ENGINE_MODE=local-llm`: LocalLLMEngineV1 사용
  - `DEMO_MODE=live, ENGINE_MODE=rule`: LocalRuleEngineV1Adapter 사용
- **엔진 선택 로직**: `getEngineModeFromEnv()` 및 `getSuggestEngine()` 테스트

#### OS Dashboard 가드 테스트
- **스키마 검증**: `engine` 섹션 포함 및 구조 검증
- **Primary Mode 검증**: `primary_mode`가 올바른 EngineMode 타입인지 확인
- **Counts 검증**: 모든 엔진 모드의 counts가 number 타입인지 확인
- **회귀 테스트**: 기존 pilot/health/risk/queue/window 섹션 유지 확인

## 기술적 개선

### 데이터베이스
- **새로운 View**: `accounting_os_engine_summary` 뷰 추가
  - 지난 24시간 기준 집계
  - 테넌트별, 엔진 모드별 카운트
- **마이그레이션**: `010_os_engine_summary.sql` 적용

### BFF 개선
- **환경 변수 로딩**: `dotenv` 패키지 추가하여 `.env` 파일 자동 로드
- **Pool 생성 개선**: `os-dashboard.ts`에서 직접 Pool 생성하여 DATABASE_URL 보장
- **에러 로깅**: OS Dashboard 오류 시 상세 로그 출력

### 타입 안정성
- **EngineMode 타입**: 엔진 모드를 타입으로 강제하여 오타 방지
- **SuggestEngineMeta**: 엔진 메타데이터 타입 정의
- **SuggestEngine 인터페이스**: `meta`, `isReady`, `initialize()` 메서드 추가

## 변경된 파일

### App (app-expo)
- `src/hud/engines/types.ts`: EngineMode, SuggestEngineMeta 타입 추가
- `src/hud/engines/index.ts`: getEngineModeFromEnv(), 엔진 선택 로직 개선
- `src/hud/engines/local-llm.ts`: LocalLLMEngineV1 구현
- `src/ui/AccountingHUD.tsx`: 엔진 상태 표시 및 초기화 로직
- `src/hud/accounting-api.ts`: X-Engine-Mode 헤더 전송

### Server (bff-accounting)
- `src/routes/os-dashboard.ts`: engine 섹션 추가, Pool 직접 생성
- `src/routes/suggest.ts`: X-Engine-Mode 헤더 수집 및 Audit 기록
- `src/index.ts`: dotenv 로딩 추가

### Server (data-pg)
- `sql/migrations/010_os_engine_summary.sql`: 엔진 모드 집계 뷰 생성

### Web (ops-console)
- `src/pages/os/OsDashboard.tsx`: Engine Mode 카드 추가

### Test
- `packages/app-expo/src/hud/engines/__tests__/engine-modes.test.ts`: 엔진 모드 테스트 추가
- `packages/bff-accounting/test/os-dashboard-guards.test.mjs`: engine 섹션 검증 추가

## 환경 변수

### App (HUD)
- `EXPO_PUBLIC_ENGINE_MODE`: 엔진 모드 선택 (`mock` | `rule` | `local-llm` | `remote`)
- `EXPO_PUBLIC_DEMO_MODE`: Demo 모드 (`mock` | `live`)

### Server (BFF)
- `DATABASE_URL`: PostgreSQL 연결 문자열 (`.env` 파일에서 로드)

## 마이그레이션 가이드

### 1. 데이터베이스 마이그레이션
```bash
npm run db:migrate
```

### 2. 환경 변수 설정
```bash
# .env 파일에 추가
DATABASE_URL=postgres://app:app@localhost:5432/app
```

### 3. BFF 재시작
```bash
npm run build --workspace=@appcore/bff-accounting
npm run dev:bff
```

### 4. HUD 환경 변수 설정
```bash
# Live 모드에서 온디바이스 LLM 사용
EXPO_PUBLIC_DEMO_MODE=live
EXPO_PUBLIC_ENGINE_MODE=local-llm
npm run demo:app:live
```

## 알려진 제한사항

1. **CS 도메인**: CS HUD는 아직 엔진 모드 전환이 지원되지 않습니다 (계속 Stub 모드)
2. **실제 LLM 연동**: 현재 LocalLLMEngineV1는 DummyLLMAdapter를 사용하며, 실제 LLM 라이브러리 연동은 다음 스프린트에서 진행 예정
3. **엔진 모드 전환**: 런타임 중 엔진 모드 전환은 지원되지 않습니다 (환경 변수 변경 후 재시작 필요)

## 다음 단계 (R9)

1. **CS 도메인 본격 구현**: CS HUD에 엔진 모드 전환 지원
2. **실제 LLM 연동**: LocalLLMEngineV1를 실제 로컬 모델(gguf/onnx)과 연결
3. **엔진 성능 비교**: 엔진 모드별 성능 비교 리포트 도구 개발
4. **UX 개선**: LLM 추론 실패/시간초과에 대한 Fallback UX 개선

## 참고 문서

- [R8S2_SPRINT_BRIEF.md](./R8S2_SPRINT_BRIEF.md) - 스프린트 개요
- [R8S2_TICKETS.md](./R8S2_TICKETS.md) - 상세 티켓 목록
- [DEMO_15MIN_SCRIPT.md](./DEMO_15MIN_SCRIPT.md) - 데모 스크립트 (업데이트됨)
- [PILOT_ENV_SETUP.md](./PILOT_ENV_SETUP.md) - 파일럿 환경 설정 (업데이트됨)

