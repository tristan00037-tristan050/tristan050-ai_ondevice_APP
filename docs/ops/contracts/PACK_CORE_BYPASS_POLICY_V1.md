# PACK_CORE_BYPASS_POLICY_V1

PACK_CORE_BYPASS_POLICY_V1_TOKEN=1

- 목적: 업무팩(pack)이 코어(정책/기록/라우팅/반출/검증)를 우회하지 못하게 한다.
- 규칙: pack은 템플릿/룰/용어 확장만 허용한다.
- 금지:
  - pack에서 core policy/router/egress/ops_hub 계열 모듈 import 금지
  - pack manifest에 routing_override/egress_mode/record_mode 등 우회 필드 금지
- verify=판정만, fail-closed, meta-only/raw=0 유지
