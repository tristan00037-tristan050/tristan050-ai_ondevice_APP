# R9-S1 스프린트 개요 (초안)

## 스프린트 정보

- **이름**: R9-S1 – CS Domain Implementation / LLM Model Integration
- **기간**: TBD
- **목표 한 줄 요약**: R8-S2에서 완성한 엔진 모드/온디바이스 LLM 인프라 위에, (1) CS 도메인 본격 기능 또는 (2) LocalLLM 실모델 연동 중 하나를 1차로 올리는 스프린트

## 배경

R7-R8에서 이미 회계 도메인 + 엔진 코어 + CS 스켈레톤까지 완성되었습니다. R9에서는 다음 두 축 중 하나 또는 둘 다를 가져가면 자연스럽습니다:

1. **CS 도메인 본격 구현 (R9-CS 라인)**
2. **On-device LLM 품질/UX 고도화 (R9-LLM 라인)**

## 목표 (Goals) - 선택적

### 옵션 A: CS 도메인 본격 구현

1. **service-core-cs에 실제 CS 티켓/상담 요약 로직 1차 도입**
   - CS 티켓 데이터 모델 정의
   - 상담 요약 로직 구현
   - CS 도메인 Audit 이벤트 정의

2. **CsHUD에서 간단한 "최근 티켓 리스트 + 요약" 기능 연결**
   - CS HUD에 티켓 리스트 UI 추가
   - 상담 요약 표시 기능
   - CS 도메인 SuggestEngine 연동

3. **/v1/cs/os/dashboard 실제 집계 API 및 웹 카드 1차 구현**
   - CS OS Dashboard API 구현
   - CS 집계 뷰 생성
   - Ops Console에 CS 카드 추가

### 옵션 B: On-device LLM 품질/UX 고도화

1. **LocalLLMEngineV1를 실제 로컬 모델(예: gguf/onnx)과 연결하는 Adapter 스프린트**
   - 실제 LLM 라이브러리 연동 (예: llama.cpp, onnxruntime)
   - 모델 로딩 및 추론 파이프라인 구현
   - 모델 버전 관리 및 캐싱

2. **LLM 추론 실패/시간초과에 대한 UX/Fallback 개선**
   - 추론 실패 시 자동 Fallback (Rule 엔진)
   - 시간초과 처리 및 사용자 피드백
   - 추론 상태 표시 (로딩, 진행률 등)

3. **Engine 모드별 성능 비교 리포트 초안(script) 작성**
   - 엔진 모드별 추론 시간 측정
   - 정확도 비교 리포트
   - 성능 메트릭 수집 및 시각화

## 범위 (Scope) - 선택적

### CS 도메인 구현 (옵션 A)

- **App (A-10)**
  - CsHUD 티켓 리스트 UI 구현
  - CS SuggestEngine 연동
  - CS 도메인 Audit 이벤트 전송

- **Server (S-09)**
  - service-core-cs 패키지 본격 구현
  - CS 티켓 데이터 모델 및 Repository
  - /v1/cs/os/dashboard API 구현

- **Server (Data)**
  - CS Audit 이벤트 테이블/뷰 생성
  - CS 집계 쿼리 구현

- **Web (W-10)**
  - Ops Console CS Dashboard 카드 추가
  - CS 티켓 리스트 페이지 (선택)

### LLM 모델 연동 (옵션 B)

- **App (A-11)**
  - 실제 LLM 라이브러리 Adapter 구현
  - 모델 로딩 및 초기화 로직
  - 추론 실패/시간초과 처리

- **App (A-12)**
  - 추론 상태 표시 UI 개선
  - Fallback UX 개선
  - 성능 메트릭 수집

- **Scripts**
  - 엔진 모드별 성능 비교 리포트 스크립트
  - 정확도 비교 도구

## 비범위 (Non-goals)

1. **두 옵션을 동시에 진행하지 않음**
   - R9-S1에서는 CS 또는 LLM 중 하나만 선택하여 집중

2. **프로덕션 수준의 LLM 모델 최적화**
   - 기본적인 모델 연동만 구현
   - 최적화는 다음 스프린트로

3. **CS 도메인 전체 워크플로우 완성**
   - 기본 티켓 리스트 및 요약만 구현
   - 고급 기능은 다음 스프린트로

## Definition of Done

### CS 도메인 구현 (옵션 A)
- [ ] CsHUD에서 최근 티켓 리스트 조회 가능
- [ ] CS SuggestEngine이 실제 로직을 사용하여 요약 생성
- [ ] /v1/cs/os/dashboard API가 실제 데이터를 반환
- [ ] Ops Console에 CS 카드가 표시됨

### LLM 모델 연동 (옵션 B)
- [ ] LocalLLMEngineV1가 실제 로컬 모델(gguf/onnx)과 연결됨
- [ ] 모델 추론 실패 시 자동으로 Rule 엔진으로 Fallback
- [ ] 엔진 모드별 성능 비교 리포트 스크립트가 동작함
- [ ] 추론 상태가 사용자에게 명확히 표시됨

## 결정 사항

**R9-S1에서는 CS 도메인 구현 또는 LLM 모델 연동 중 하나를 선택하여 진행합니다.**

선택 기준:
- 비즈니스 우선순위
- 기술적 복잡도
- 팀 리소스

## 참고 문서

- [R8S2_SPRINT_BRIEF.md](./R8S2_SPRINT_BRIEF.md) - 이전 스프린트 개요
- [R8S2_RELEASE_NOTES.md](./R8S2_RELEASE_NOTES.md) - R8-S2 릴리스 노트
- [R8S1_IMPLEMENTATION_GUIDE.md](./R8S1_IMPLEMENTATION_GUIDE.md) - CS 스켈레톤 구현 가이드

