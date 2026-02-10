# WORKFLOW_PREFLIGHT_SSOT_V1

목표:
- product-verify* 워크플로는 verify 전에 preflight로 필요한 준비물(dist/node_modules 등)을 갖춘다.
- verify는 판정만 수행한다(설치/다운로드/빌드 유입 금지).
- 워크플로에 고정 토큰을 넣어 "preflight 누락"을 자동 차단한다.

SSOT 토큰(문서):
WORKFLOW_PREFLIGHT_SSOT_V1_TOKEN=1

워크플로 토큰(고정 문자열):
PREP_TOKEN=1

규칙:
- product-verify* 워크플로의 preflight step 주석에 반드시 PREP_TOKEN=1 포함
- 누락 시 fail-closed(BLOCK)

