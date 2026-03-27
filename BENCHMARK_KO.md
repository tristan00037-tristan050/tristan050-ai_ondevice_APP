# 온디바이스 AI 경쟁 구도와 차별화 전략 (2026-03-27 기준)

## 1. 왜 Qwen3-4B가 현재 지시서와 잘 맞는가
- Qwen3는 thinking / non-thinking 전환을 한 모델 안에서 지원합니다.
- Qwen3 공식 자료에는 `enable_thinking=True` 가 기본값이라고 명시되어 있어, 학습 파이프라인에서는 이를 **명시적으로 False** 로 고정해야 합니다.
- Qwen3 공식 GitHub는 Qwen3가 **MNN 모바일 실행 경로**를 갖고 있음을 명시합니다.
- Qwen3-4B 모델 카드는 Apache 2.0 라이선스를 표기합니다.

## 2. 글로벌 비교 관찰

### A. Google / Android
- Gemini Nano는 Android 공식 문서에서 **네트워크 없이 기기 내 생성형 AI** 를 지원한다고 설명합니다.
- Android AI 스택은 Gemini Nano + ML Kit Prompt API + LiteRT 중심으로 진화 중입니다.
- 시사점: Android 앱에 붙이는 운영 패턴, 권한, UX, 배터리 설계는 Google 흐름을 적극 벤치마킹해야 합니다.

### B. Apple
- Apple Intelligence는 공식 페이지에서 **on-device processing** 을 핵심으로 내세우고,
  더 복잡한 요청은 Private Cloud Compute로 확장한다고 설명합니다.
- 시사점: 우리 제품도 "전부 로컬"만이 아니라 **로컬 우선 + 검증 가능한 선택적 확장** 구조를 중장기 아키텍처로 고려할 가치가 있습니다.

### C. Qualcomm
- Qualcomm AI Hub는 실제 Qualcomm 기기에서 모델 성능을 검증하고,
  LiteRT / ONNX Runtime / Qualcomm AI Stack으로 변환·프로파일링하는 워크플로를 제공합니다.
- 시사점: 추상적 벤치마크보다 **실기기 프로파일링 자동화** 가 경쟁력의 핵심입니다.

### D. ExecuTorch
- ExecuTorch는 PyTorch의 통합 on-device AI 프레임워크로,
  스마트폰부터 임베디드 장치까지 배포 경로를 제공합니다.
- 시사점: MNN 단일 경로만이 아니라 **ExecuTorch 백엔드 실험 경로** 를 병행 확보하면 공급망 리스크를 낮출 수 있습니다.

### E. MNN
- MNN은 Qwen3 모바일 지원과 오프라인 iOS/Android 앱 예시를 공개하고 있습니다.
- 시사점: 현재 지시서의 MNN 중심 전략은 2026년에도 충분히 유효합니다.

### F. OpenAI / Claude Code / Gemini
- OpenAI와 Claude Code의 공식 문서는 공통적으로 **도구 사용·멀티파일 작업·개발 자동화** 역량을 강화하고 있습니다.
- Google Gemini 공식 문서 역시 built-in tools와 function calling 결합을 강조합니다.
- 시사점: 모델 본체 성능만으로는 부족하고, **로컬 툴 실행, 함수 호출, 검증 루프** 가 제품 경쟁력의 절반 이상을 차지합니다.

## 3. 우리 팀이 반드시 메워야 하는 격차

### 1) 모델 자체
- 한국어 업무형 instruction 품질
- think/no-think 정책 일관성
- 안전 거부 응답의 한영 이중 언어 일관성

### 2) 배포/runtime
- 4bit → 모바일 runtime 변환
- Android/iOS latency 회귀 측정
- memory footprint 관리
- thermal throttling 장기 테스트

### 3) 에이전트 기능
- 도구 호출 JSON 안정성
- 실패 시 재시도/복구 전략
- 장문 컨텍스트 축약과 메모리 관리
- 온디바이스 RAG 캐시

### 4) 검증 체계
- smoke test, regression, safety regression, latency regression, tool-call schema regression을 분리해야 함
- PR 단계에서는 구조/정합성,
  GPU 단계에서는 학습/품질,
  실기기 단계에서는 latency/열/배터리까지 나눠야 함

## 4. 차별화 우선순위 제안

### P0
- `enable_thinking=False` fail-closed
- Qwen3 chat template 일관화
- bilingual policy refusal 회귀셋
- TRL 버전 차이 자동 흡수

### P1
- MNN export 자동화
- Android/iOS latency benchmark harness
- tool-call schema constrained decoding
- prompt cache / summary cache

### P2
- think/no-think 자동 라우터
- local RAG + task memory
- adapter merge / deploy profile
- hybrid edge-cloud escalation design

## 5. 추천 KPI
- 구조 검증 성공률: 100%
- dry-run 성공률: 100%
- tool-call schema 준수율: 98%+
- bilingual refusal 탐지 재현율: 99%+
- Android/iOS p95 latency: 제품 목표치 이내
- long-session memory degradation: 회귀 테스트로 관리

## 6. 결론
현재 지시서 기준에서 가장 현실적인 승부 포인트는
**Qwen3-4B + QLoRA + non-thinking 강제 + MNN/모바일 회귀 검증 자동화** 입니다.

단순히 "작동하는 온디바이스 LLM" 이 아니라,
**검증 가능한 로컬 에이전트 파이프라인** 으로 가야 OpenAI/Claude/Gemini 계열과의 체감 격차를 줄일 수 있습니다.
