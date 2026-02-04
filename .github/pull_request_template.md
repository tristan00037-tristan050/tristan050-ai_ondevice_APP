## 개요

- 이 PR의 목적을 한 줄로 적어주세요.

예)
- `CS HUD에 SuggestEngine/LocalLLM Stub을 연동하여, 온디바이스 LLM 패턴을 검증합니다.`
- `회계 HUD에서 사용하던 Offline Queue 패턴을 공통 컴포넌트로 분리합니다.`

---

## Enterprise OS 관점 (필수로 한 줄 이상 작성)

- 이번 변경이 **어떤 도메인(HUD)**(예: 회계/CS/HR/법무/보안/반도체/조선/소프트웨어/개인정보)을 대상으로 하고,
- 온디바이스 + 사내 게이트웨이 OS 구조에 **어떻게 기여하는지**를 한 줄 이상으로 설명해 주세요.

예)
- `이번 변경은 CS HUD에서 SuggestEngine/LocalLLM 패턴을 검증하여, 이후 HR/법무/보안 HUD에도 재사용 가능한 온디바이스 엔진 구조를 강화합니다.`

---

## 변경 사항

- [ ] 코드
- [ ] 테스트
- [ ] 문서 (Playbook / 설계 노트 / 티켓 등)

---

## 체크리스트 (Enterprise OS 기준)

- [ ] Mock 모드 플로우를 확인했습니다. (`DEMO_MODE=mock`, HTTP/WS 0건 유지)
- [ ] Live 모드 플로우를 확인했습니다. (`DEMO_MODE=live`, BFF/DB와의 통신)
- [ ] OS 정책 헤더(X-Tenant, X-User-Id, X-User-Role)를 준수합니다.
