# [R10S3-E06-1] local-llm-v1 PoC 구조 기준선

## OS Contribution

이 PR은 **local-llm-v1 실제 모델 PoC를 위한 구조적 기준선**을 확립합니다. 실제 모델 라이브러리 연동은 별도 브랜치/티켓으로 진행됩니다.

### 주요 변경사항

1. **EngineMeta 확장**
   - `variant`: 엔진 버전 구분 (예: 'local-llm-v0', 'local-llm-v1')
   - `stub`: Stub 여부 (true: 더미/시뮬레이션, false: 실제 모델)
   - `supportedDomains`: 지원 도메인 목록

2. **LocalLLMEngineV1 meta 업데이트**
   - Mock 모드: `variant: 'local-llm-v0'`, `stub: true` (Stub 유지)
   - Live 모드: `variant: 'local-llm-v1'`, `stub: false` (실제 모델 준비)
   - `supportedDomains: ['accounting', 'cs']` 추가

3. **llmUsage.ts 업데이트**
   - `meta.variant`, `meta.stub` 필드 사용
   - Usage 이벤트에 엔진 버전 및 Stub 여부 포함

## Playbook Compliance

- ✅ **온디바이스 우선**: Mock 모드에서 Network 0 유지 (Stub 사용)
- ✅ **게이트웨이 경계**: HUD→BFF 경계 유지, 텍스트 원문 Audit 금지 준수
- ✅ **Mock/Live 쌍**: Mock 모드에서 Stub 유지, Live 모드에서 실제 모델 준비
- ✅ **OS 레이어 재사용성**: EngineMeta 확장으로 다도메인 지원 구조 준비
- ✅ **KPI/감사**: variant, stub 필드로 엔진 버전 및 Stub 여부 추적 가능

## 변경 파일

- `packages/app-expo/src/hud/engines/types.ts` - EngineMeta 확장
- `packages/app-expo/src/hud/engines/local-llm.ts` - meta 업데이트 및 분기 로직
- `packages/app-expo/src/hud/telemetry/llmUsage.ts` - meta 필드 사용

## 다음 단계 (별도 브랜치/티켓)

실제 모델 라이브러리 연동은 다음 단계에서 진행:
- 실제 온디바이스 LLM 라이브러리 선택 (llama.cpp / ONNX Runtime / TensorFlow Lite)
- RealLLMAdapter 구현
- Mock/Live 모드에서 실제 모델 동작 확인

## QA

- [ ] 타입 체크 통과
- [ ] Mock 모드에서 variant='local-llm-v0', stub=true 확인
- [ ] Live 모드에서 variant='local-llm-v1', stub=false 확인 (현재는 아직 DummyLLMAdapter 사용)
- [ ] Usage 이벤트에 variant, stub 필드 포함 확인

