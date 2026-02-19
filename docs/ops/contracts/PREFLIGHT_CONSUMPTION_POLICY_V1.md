# PREFLIGHT_CONSUMPTION_POLICY_V1

PREFLIGHT_CONSUMPTION_POLICY_V1_TOKEN=1

- 목적: 필수 워크플로는 반드시 ./.github/actions/preflight_v1 를 사용한다.
- 금지: 워크플로에서 bff-accounting 수동 빌드, .build_stamp.json 직접 생성/언급 등 "중복 prep 경로"는 0이어야 한다.
- 원칙: 준비(build/install/stamp)는 preflight에서만, verify는 판정만.
