# P3 Common Single Failure Points v1 (meta-only)

P3 PR마다 아래 6개는 BLOCK 규칙으로 강제한다.

1) verify에서 rg 의존(도구 편차)
2) canonicalize 중복 구현(드리프트)
3) fingerprint 입력 정책이 정적 스캔만(우회 가능)
4) golden vectors 파일 오염(원문/배열/긴 문자열)
5) energy_proxy=cpu_time_ms "항상 0" 무력화
6) trace bind/auth 검증이 문자열 탐지만(오탐/미탐)

불가침:
- verify는 판정만(설치/다운로드/빌드 유입 금지)
- 원문 저장 0(meta-only만)
- DoD 키 추가만
- fail-closed

