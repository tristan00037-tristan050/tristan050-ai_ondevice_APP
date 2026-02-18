# ENERGY_PROXY_POLICY_V2

ENERGY_PROXY_POLICY_V2_TOKEN=1

- 목적: energy proxy cpu_time_ms v2 단일 소스 + 측정 창 SSOT, fail-closed (p50>0, sum>0, expected fixture 필수).
- 측정 창: 10회 실행, p50 > 0, 10회 합 > 0.
- expected fixture 없으면 BLOCK. 스킵 분기 정적 탐지 시 BLOCK.
