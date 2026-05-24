# Butler IP3 v1.3 Full-Stack Routing / Telemetry / Claim-Guard Pack

## STATUS

`IP3_V1_3_FULL_STACK_SEALABLE_DEVELOPMENT_PACK`

이 패키지는 IP #3 On-device Context Routing Engine v1.3을 개발지시서 구조(Subphase 3.0~3.8)에 맞춰 코드, 테스트, 증빙, 게이트, 문서, CI runner로 확장한 산출물입니다.

이번 ZIP은 운영 완료본이 아닙니다. 별도 Windows 물리 장치, 실제 Butler 앱 배포 hook, IP #2 live runtime PEP, IP #1 v5.4 forward_verified evidence가 아직 외부에서 제공되지 않았으므로 아래 claim은 모두 금지됩니다.

- `APPROVED_FOR_PRODUCTION`
- `APPROVED_FOR_PHYSICAL_WINDOWS_LAB`
- `production_hook_deployed=true`
- `local_1_7b_forward_verified=true`
- `release_claim_allowed=true`

## 완성 범위

1. Subphase 3.0: 5 type JSON schema + routing_state enum + schema gate
2. Subphase 3.0A: threat model + failure taxonomy + claim guard
3. Subphase 3.1: CPU/RAM/battery/thermal/network 5중 측정 schema와 Windows/macOS/Linux collector
4. Subphase 3.2: device class A/B/C/D classifier
5. Subphase 3.3: UserContext 4축 점수화 + raw text 저장 금지
6. Subphase 3.4: 4단 routing engine + executable verification
7. Subphase 3.5: routing hook 11단계 replay + IP2/IP1 bridge contract
8. Subphase 3.6: metadata + audit hash chain + digest-only evidence
9. Subphase 3.7: fail-safe live injection 6시나리오
10. Subphase 3.8: adaptive routing profile with privacy/digest-only updates
11. 2026 벤치마킹 반영: LLM router benchmark, vLLM semantic router, Zero Trust PEP/PDP, OpenTelemetry-style metrics, GitHub Actions 3OS CI
12. Package seal: ASCII root, dirty artifact 0, nested zip 0, SHA-256 manifest, claim guard

## 로컬 self-check

```bash
bash scripts/ops/run_v13_full_stack_local_gates.sh .
```

성공 시 핵심 출력:

```text
UNIT_TESTS_OK
ROUTING_SCHEMA_GATE_OK
THREAT_MODEL_GATE_OK
CLAIM_GUARD_OK
RAW_CONTENT_SCAN_OK
EVIDENCE_TAXONOMY_GATE_OK
LIVE_APP_ROUTING_HOOK_OK_SAMPLE
IP2_PEP_LIVE_BRIDGE_OK_SAMPLE
IP1_MODEL_STATUS_BRIDGE_OK forward_verified=false routing_executable=false
ROUTING_LATENCY_BUDGET_OK
FAIL_SAFE_LIVE_INJECTION_OK_SAMPLE scenarios=6
PRODUCT_CANDIDATE_FULL_REPLAY_OK_SAMPLE
ALL_PLATFORM_TELEMETRY_FAIL_CLOSED_OK
CLEAN_PACKAGE_OK
SHA256_MANIFEST_OK
IP3_V1_3_FULL_STACK_LOCAL_GATES_OK
```

`ALL_PLATFORM_TELEMETRY_FAIL_CLOSED_OK`는 이 ZIP의 정상 상태입니다. 외부 GitHub Actions 또는 실제 3플랫폼 telemetry artifact가 아직 포함되지 않았기 때문입니다.

## CI_LAB 승격

`.github/workflows/ip3-v13-full-stack-ci-lab.yml`을 레포에 반영하고 실행하면 `ubuntu-latest`, `macos-latest`, `windows-latest` runner에서 telemetry를 생성하고 aggregate job에서 3플랫폼 gate를 수행합니다. 해당 실행이 성공해야만 `APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB`를 기록할 수 있습니다.

## Windows VM / Physical LAB

Windows VM은 `windows/collect_windows_telemetry_vm_lab.ps1`, 실제 Windows 노트북은 `windows/collect_windows_telemetry_physical_lab.ps1`을 실행합니다. VM 결과는 VM_LAB으로만 인정하며 PHYSICAL_LAB으로 승격하지 않습니다.

## 금지 claim

- sample/ci_lab 증빙으로 production claim 금지
- Windows telemetry 없이 all-platform strict pass claim 금지
- 실제 Butler app hook 없이 production hook claim 금지
- IP #1 v5.4 forward_verified evidence 없이 local_1_7b routing executable true 금지
- raw prompt, raw user text, raw log, raw path, raw hostname, raw IP 저장 금지
