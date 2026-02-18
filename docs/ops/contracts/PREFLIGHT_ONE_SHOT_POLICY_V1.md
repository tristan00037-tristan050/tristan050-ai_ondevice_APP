# PREFLIGHT_ONE_SHOT_POLICY_V1

PREFLIGHT_ONE_SHOT_POLICY_V1_TOKEN=1

- 목적: 로컬과 CI가 동일한 preflight를 사용한다.
- 불가침: verify=판정만. build/install/download/network는 verify에서 금지.
- preflight에서만 dist/stamp를 생성한다.
- stamp는 meta-only JSON이며, 비교 대상 필드를 고정한다.

