# WORKFLOW_PREFLIGHT_SSOT_V1
WORKFLOW_PREFLIGHT_SSOT_V1_TOKEN=1

규칙(고정):
- product-verify-*.yml 워크플로 파일에는 반드시 # PREP_TOKEN=1 토큰이 포함되어야 한다.
- verify는 설치/다운로드/빌드 금지. preflight 준비는 workflow에서만 수행한다.
- 토큰이 누락된 워크플로는 기준선에서 즉시 BLOCK 한다.
