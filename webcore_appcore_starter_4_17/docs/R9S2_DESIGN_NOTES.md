# R9-S2 설계 노트

## 현재 구현 평가

### 완료된 티켓
- ✅ [R9S2-SC10-1] CS LLM 서비스 skeleton
- ✅ [R9S2-A11-1] CsHUD SuggestEngine 연결

### 설계 강점

#### 1. 레이어링 분리
- **csLLMService**: "LLM에게 어떤 말을 시킬지" 책임
- **엔진/어댑터**: "LLM에게 어떻게 호출할지" 책임
- 이 경계를 유지하면 프롬프트 튜닝/모델 교체가 용이

#### 2. 확장 가능한 타입 구조
- `CsLLMContext`: 티켓 + 히스토리 + 메타까지 담을 수 있는 구조
- `CsLLMResponse`: 구조화된 응답 (요약 + 답변 + 태깅 등 확장 용이)
- 도메인/태스크 기반 payload 구조

#### 3. Mock 모드 네트워크 0 유지
- `DEMO_MODE=mock`일 때 `ENGINE_MODE`와 관계없이 네트워크 요청 0 보장

## 설계 관점 개선점

### 1. 메서드 폭발 방지

**현재 상태:**
- `LocalLLMEngineV1`에 `suggestForCs()` 메서드 추가
- 현재 단계에서는 명시적 메서드가 이해하기 쉬움

**향후 개선 방향 (R9-S2 후반 또는 R10):**
```typescript
// 도메인/태스크 기반 payload로 통합 고려
engine.suggest({
  domain: 'cs',
  task: 'reply',
  context: csContext,
  ...
})
```

**전략:**
- 현재: 명시적 메서드 → 이후 내부 라우팅 도입 순서로 진행
- 점진적 리팩토링으로 통합

### 2. csLLMService 역할 명확화

**책임 분리:**
- ✅ **csLLMService**: LLM 입력/출력 형식 설계, 프롬프트 생성
- ✅ **엔진/어댑터**: 호출 방식, latency, 에러 처리

**유지해야 할 원칙:**
- 도메인 로직은 csLLMService에 집중
- 엔진/어댑터는 교체 가능하도록 인터페이스만 의존

## 다음 단계

### 1. Mock/Live 모드 빠른 수동 확인

**Mock 모드:**
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```
- CS 탭 → "요약/추천" 버튼 클릭
- Network 탭에서 HTTP/WS 0건 확인

**Live 모드:**
```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```
- 버튼 클릭 시 HUD가 멈추지 않는지 확인
- 로딩/완료 상태가 자연스러운지 확인

### 2. [R9S2-A11-2] CS 전용 LLM 타입 정의

**목표:**
- `engines/types.ts`에 CS 전용 타입 추가
- "회계용 payload"와 "CS용 payload" 구분

**추가할 타입:**
```typescript
// CS 태스크 타입
export type CsLLMTask = 'reply' | 'summary' | 'categorize';

// CS Suggest Payload
export interface CsSuggestPayload {
  task: CsLLMTask;
  inquiry: string;
  ticketId?: number;
  history?: CsTicket[];
}

// CS Suggest Result
export interface CsSuggestResult {
  suggestions: CsResponseSuggestion[];
  summary?: string;
  explanation?: string;
}
```

**효과:**
- 타입 안전성 확보
- UI/BFF/로그까지 타입 안전하게 전달 가능

### 3. [R9S2-A11-3] LocalLLMEngineV1 CS 어댑터 구현

**구현 순서:**
1. LLM 호출 전:
   - `csLLMService.buildCsLLMContext()` 호출
   - `csLLMService.buildReplyPrompt()` 호출

2. LLM 호출 (Stub):
   - `setTimeout`으로 1~2초 지연 시뮬레이션
   - HUD 로딩 UX 확인

3. LLM 호출 후:
   - `csLLMService.recordSuggestionAudit()`에 결과 전달
   - 현재는 Stub로 로그만 출력해도 OK

**Mock 모드:**
- 네트워크 요청 없이 더미 응답만 반환
- 지연 없이 즉시 응답

## 아키텍처 원칙

### 1. 레이어 분리
```
HUD (UI)
  ↓
SuggestEngine (엔진 선택)
  ↓
LocalLLMEngineV1 (추론 엔진)
  ↓
csLLMService (도메인 로직)
  ↓
실제 LLM 모델/어댑터
```

### 2. 책임 분리
- **HUD**: 사용자 인터랙션, UI 상태 관리
- **SuggestEngine**: 엔진 선택, 모드 분기
- **LocalLLMEngineV1**: 추론 호출, 에러 처리
- **csLLMService**: 도메인 로직, 프롬프트 설계

### 3. 확장성
- 도메인 추가 시: 새로운 LLM 서비스 + 엔진 도메인 지원
- 모델 교체 시: 어댑터만 교체, 도메인 로직 유지
- 태스크 추가 시: 타입 확장, 메서드 추가

## 체크리스트

### 현재 완료
- [x] CS LLM 서비스 인터페이스 skeleton
- [x] CsHUD SuggestEngine 연결
- [x] LocalLLMEngineV1 CS 도메인 지원

### 다음 작업
- [ ] Mock/Live 모드 수동 확인
- [ ] CS 전용 LLM 타입 정의
- [ ] LocalLLMEngineV1 CS 어댑터 구현
- [ ] Mock 모드 네트워크 0 회귀 테스트
- [ ] Live 모드 엔진 모드별 동작 테스트

