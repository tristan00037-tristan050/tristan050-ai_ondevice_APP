# ENERGY_PROXY_POLICY_V1

ENERGY_PROXY_POLICY_V1_TOKEN=1

정의(고정):
- cpu_time_ms_v1 = (process.cpuUsage().user + process.cpuUsage().system) / 1000.0
- 단위: cpuUsage는 microseconds(µs), ms는 부동소수 유지(정수 반올림 금지)

