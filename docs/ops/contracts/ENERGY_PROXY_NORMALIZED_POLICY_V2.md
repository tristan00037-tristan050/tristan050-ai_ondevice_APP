# ENERGY_PROXY_NORMALIZED_POLICY_V2

ENERGY_PROXY_NORMALIZED_POLICY_V2_TOKEN=1

- 목적: cpu_time 기반 energy proxy를 per-inference로 정규화하여 비교 가능하게 만든다.
- 불가침: meta-only / 원문0 / verify=판정만 / fail-closed
- 정의:
  - cpu_time_ms = (user_us + system_us) / 1000.0  (float 유지)
  - normalized_cpu_time_ms = cpu_time_ms / inference_count
- fail-closed:
  - inference_count <= 0 이면 BLOCK
  - p50 <= 0 이면 BLOCK
  - expected fixture가 없으면 BLOCK
