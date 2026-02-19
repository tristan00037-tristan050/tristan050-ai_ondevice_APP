# NO_RAW_IN_LOGS_POLICY_V1

NO_RAW_IN_LOGS_POLICY_V1_TOKEN=1

목표
- 원문0(meta-only) 규율을 로그/예외/리포트/증빙 전 구간으로 전수 강제한다.

fail-closed
- 민감 패턴(토큰/비밀번호/키) 발견 시 즉시 BLOCK
- 긴 라인(덤프) 차단: 한 줄 2000자 초과 존재 시 즉시 BLOCK
- 금지키 탐지: JSON 키 선언 형태로 발견 시 즉시 BLOCK (값 문자열은 오탐 방지를 위해 제외)

주의
- verify는 판정만 수행한다(네트워크/설치/다운로드 금지).
