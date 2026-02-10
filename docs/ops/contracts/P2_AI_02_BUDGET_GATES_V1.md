# P2-AI-02 Budget Gates v1 (meta-only)

목표:
- latency_ms / mem_peak_mb / energy_proxy(cpu_time_ms)를 meta-only로 측정
- SSOT 예산과 비교
- 측정 누락은 즉시 fail-closed(BLOCK)
- 예산 초과인데 PASS 경로 0

DoD keys (added-only):
- AI_RESOURCE_BUDGET_LATENCY_OK=1
- AI_RESOURCE_BUDGET_MEM_OK=1
- AI_RESOURCE_BUDGET_ENERGY_PROXY_OK=1
- AI_BUDGET_MEASUREMENTS_PRESENT_OK=1
- AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1

BLOCK:
- 측정 누락인데 PASS
- 예산 초과인데 PASS
- energy_proxy 정의가 SSOT 없이 변경

검증(최종 앵커):
- bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"

