# IP3 v1.3 Approval Matrix

| Evidence class | Windows gate | All-platform gate | Handoff status | Physical Windows claim | Production claim |
|---|---|---|---|---|---|
| ci_lab | `WINDOWS_REAL_TELEMETRY_OK_CI_LAB` | `ALL_PLATFORM_TELEMETRY_OK_CI_LAB` | `APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB` | 금지 | 금지 |
| vm_lab | `WINDOWS_REAL_TELEMETRY_OK_VM_LAB` | `ALL_PLATFORM_TELEMETRY_OK_VM_LAB` | `APPROVED_FOR_AI_ONDEVICE13_HANDOFF_VM_LAB` | 금지 | 금지 |
| physical_lab | `WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB` | `ALL_PLATFORM_TELEMETRY_OK_PHYSICAL_LAB` | `APPROVED_FOR_AI_ONDEVICE13_HANDOFF_PHYSICAL_WINDOWS_LAB` | 허용 | 금지 |
| production | 현재 비활성 | 현재 비활성 | 현재 비활성 | 운영 증빙 필요 | 운영 증빙 필요 |

## Gate precedence

높은 등급 claim은 낮은 등급 evidence로 충족되지 않습니다. `ci_lab < vm_lab < physical_lab < production` 순서의 단조 claim 정책을 적용합니다.
