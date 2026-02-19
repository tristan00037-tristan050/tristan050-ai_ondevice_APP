# ASSIST_COMPUTE_POLICY_V1

ASSIST_COMPUTE_POLICY_V1_TOKEN=1

DEFAULT_OFF=1

# Enable conditions (must be explicitly satisfied)
# - If any condition is missing/invalid -> MUST stay OFF (fail-closed)
ENABLE_ENV_KEY=ASSIST_COMPUTE_ENABLED
ENABLE_ENV_VALUE=1

# Optional: require explicit request header to prevent accidental activation
REQUIRE_HEADER=1
HEADER_NAME=X-Assist-Compute
HEADER_VALUE=1

# Notes
- 목적: 내부 보조 컴퓨트/원격 게이트웨이 기본 OFF를 코드/게이트로 봉인한다.
- 조건 SSOT 없으면 구현/라우팅 금지. (DEFAULT_OFF=1)
- verify=판정만, meta-only/raw=0 유지.
