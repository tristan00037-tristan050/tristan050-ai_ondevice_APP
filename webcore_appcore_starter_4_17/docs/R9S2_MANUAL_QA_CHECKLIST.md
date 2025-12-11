# R9-S2 수동 QA 체크리스트

## 목표

CS 도메인에 SuggestEngine이 올바르게 연결되었는지, Mock 모드에서 네트워크 0이 유지되는지 확인합니다.

---

## 1. Mock 모드 확인 (네트워크 0 검증)

### 준비
```bash
cd webcore_appcore_starter_4_17
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```

### 확인 사항

#### 1-1. HUD 시작 확인
- [ ] HUD가 정상적으로 시작됨
- [ ] 상단 상태바에 "Mode: Mock" 표시
- [ ] 상단 상태바에 "Engine: On-device (Rule)" 또는 "Engine: Mock" 표시
  - 참고: Mock 모드에서는 `ENGINE_MODE`와 관계없이 항상 mock/rule 엔진 사용

#### 1-2. CS 탭 접근
- [ ] CS HUD 탭으로 전환
- [ ] "CS HUD" 제목 표시
- [ ] Mock 모드 배너 표시 ("ⓘ Mock 모드: 네트워크 요청이 발생하지 않습니다.")

#### 1-3. 티켓 리스트 확인
- [ ] 티켓 리스트가 표시됨 (Mock 데이터)
- [ ] 각 티켓에 "요약/추천" 버튼이 표시됨

#### 1-4. Network 탭 준비
- [ ] Chrome DevTools 열기 (F12)
- [ ] Network 탭 선택
- [ ] "Clear" 버튼으로 기존 요청 초기화

#### 1-5. "요약/추천" 버튼 클릭
- [ ] 티켓 중 하나의 "요약/추천" 버튼 클릭
- [ ] 버튼이 "추천 중..."으로 변경됨
- [ ] 잠시 후 응답이 표시됨 (Stub 응답)

#### 1-6. Network 탭 확인 (핵심)
- [ ] Network 탭에서 HTTP 요청이 **0건**인지 확인
- [ ] WebSocket 연결이 **없는지** 확인
- [ ] 모든 요청이 로컬에서 처리되었는지 확인

#### 1-7. 응답 확인
- [ ] 응답 추천 영역이 티켓 아래에 표시됨
- [ ] "[Stub] ..." 형태의 응답이 표시됨
- [ ] 버튼이 다시 "요약/추천"으로 변경됨

### 예상 결과
- ✅ Network 탭: HTTP/WS 요청 0건
- ✅ 응답: Stub 응답 즉시 표시 (지연 없음)
- ✅ 에러: 없음

---

## 2. Live 모드 확인 (엔진 모드별 동작)

### 준비
```bash
# BFF 서버가 실행 중인지 확인
# 필요시: npm run dev:bff

EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```

### 확인 사항

#### 2-1. HUD 시작 확인
- [ ] HUD가 정상적으로 시작됨
- [ ] 상단 상태바에 "Mode: Live(BFF)" 표시
- [ ] 상단 상태바에 "Engine: On-device LLM" 표시

#### 2-2. CS 탭 접근
- [ ] CS HUD 탭으로 전환
- [ ] 티켓 리스트가 로드됨 (실제 BFF에서 가져옴)
- [ ] Mock 모드 배너가 **표시되지 않음**

#### 2-3. "요약/추천" 버튼 클릭
- [ ] 티켓 중 하나의 "요약/추천" 버튼 클릭
- [ ] 버튼이 "추천 중..."으로 변경됨
- [ ] HUD가 **멈추지 않고** 로딩 상태 유지

#### 2-4. 응답 확인
- [ ] 1~2초 후 응답이 표시됨 (Stub 지연 시뮬레이션)
- [ ] 응답 추천 영역이 티켓 아래에 표시됨
- [ ] 버튼이 다시 "요약/추천"으로 변경됨

#### 2-5. 여러 티켓 테스트
- [ ] 다른 티켓의 "요약/추천" 버튼도 정상 동작
- [ ] 이전 응답이 사라지고 새로운 응답이 표시됨

### 예상 결과
- ✅ Live 모드에서 정상 동작
- ✅ 로딩 상태가 자연스럽게 표시됨
- ✅ 응답이 올바르게 표시됨

---

## 3. 엔진 모드별 동작 확인 (선택)

### 3-1. Rule 모드
```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:live
```
- [ ] 상단 상태바에 "Engine: On-device (Rule)" 표시
- [ ] "요약/추천" 버튼 클릭 시 정상 동작

### 3-2. Mock 모드 (ENGINE_MODE=local-llm)
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```
- [ ] Mock 모드에서는 `ENGINE_MODE`와 관계없이 mock/rule 엔진 사용
- [ ] Network 탭에서 요청 0건 확인

---

## 체크리스트 요약

### 필수 확인 사항
- [ ] Mock 모드: Network 탭 HTTP/WS 요청 0건
- [ ] Live 모드: "요약/추천" 버튼 정상 동작
- [ ] Live 모드: 로딩 상태 자연스러움
- [ ] 응답이 올바르게 표시됨

### 문제 발생 시
1. 콘솔 에러 확인
2. Network 탭에서 예상치 못한 요청 확인
3. `docs/R9S2_DESIGN_NOTES.md` 참고

---

## 다음 단계

수동 확인 완료 후:
- [R9S2-A11-2] CS 전용 LLM 타입 정의 진행

