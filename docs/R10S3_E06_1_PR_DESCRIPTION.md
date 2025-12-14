## 개요
R10-S3 E06-1에서 EngineMeta(variant/stub/supportedDomains)를 확장하고, LLM Usage 텔레메트리에 해당 메타를 포함시켜 "온디바이스 엔진 버전/Stub 여부"를 OS 레벨에서 일관되게 식별할 수 있게 합니다.

## Enterprise OS 관점
- 온디바이스 엔진의 버전/Stub 여부를 메타로 표준화하여, 이후 실제 모델 연동(local-llm-v1) 및 도메인 확장을 안전하게 진행할 수 있는 기준선을 고정합니다.
- Mock/Live 모드 쌍을 유지하며, HUD/Web이 외부 LLM을 직접 호출하지 않고(게이트웨이 경계 유지), 계측은 메타/지표 위주로 전달합니다.

## 변경 사항
- [x] EngineMeta 확장: variant, stub, supportedDomains 추가
- [x] LocalLLMEngineV1: 모드별(meta.variant/meta.stub) 분기 및 supportedDomains 반영
- [x] LLM Usage: meta.variant/meta.stub 사용(전송 페이로드에 포함)

## 체크리스트 (Enterprise OS 기준)
- [ ] Mock 모드: HTTP/WS 0건 유지 확인
- [ ] Live 모드: 엔진 메타(variant/stub/supportedDomains) 값이 기대대로 반영되는지 확인
- [ ] Usage/Audit: 전송 payload에 variant/stub 포함 확인
