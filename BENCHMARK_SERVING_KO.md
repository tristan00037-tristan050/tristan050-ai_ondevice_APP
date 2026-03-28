# AI-22 서빙 레이어 벤치마킹 및 차별화 메모

## 현재 번들에서 확보한 수준
- OpenAI Chat Completions 형식 호환
- SSE 스트리밍과 `[DONE]` 종료 보장
- API key / allowlist / body size 제한
- stub-first 개발 방식
- Qwen3 `enable_thinking=False` 강제
- 외부 전송 0, 응답 content 로그 금지

## 2026 경쟁 기준 대비 갭
### OpenAI
- 현재 번들은 `/v1/chat/completions` 중심입니다.
- 차기 단계에서 `Responses API`, structured outputs, function calling, prompt caching, conversation state 를 추가해야 합니다.

### Claude Code
- Claude Code/Agent SDK 수준에 맞추려면 파일 편집, 명령 실행, MCP 기반 툴 브리지, sub-agent orchestration 이 필요합니다.

### Gemini
- Gemini 수준과 격차를 줄이려면 structured outputs + built-in tools 조합, 문서 입력, 장문 컨텍스트 관리가 필요합니다.

## 우선순위 제안
1. `/v1/responses` 와 tool-calling JSON schema 도입
2. Prometheus 포맷 메트릭 + request tracing
3. token counting / prompt caching
4. TLS 종단, rate limiting, audit trail
5. MCP / 내부 도구 브리지
6. AI-21 TurboQuant 실연동 후 long-context 부하 테스트
