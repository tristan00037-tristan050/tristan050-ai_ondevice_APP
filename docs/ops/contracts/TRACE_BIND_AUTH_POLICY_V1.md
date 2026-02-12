# TRACE_BIND_AUTH_POLICY_V1

TRACE_BIND_AUTH_POLICY_V1_TOKEN=1

정책(고정):
- Trace 바인딩은 로컬 전용이어야 한다.
  허용: 127.0.0.1, ::1, ::ffff:127.0.0.1
  금지: 0.0.0.0, ::
- Trace 접근은 API 키가 "존재"하는 것만으로 통과하면 안 되고,
  verify에서 "값 비교"가 가능하도록 SSOT 토큰(TRACE_API_KEY_EXPECTED_TOKEN=1)을 함께 유지한다.

