# IP3 v1.3 CI_LAB 인계 문서

## 판정

현재 패키지 판정은 `CI_LAB_SEALABLE_HANDOFF_CANDIDATE`입니다.

`APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB`은 GitHub Actions 3플랫폼 matrix 수집과 aggregate sealing job이 성공한 뒤에만 기록됩니다.

## 인계 목적

본 패키지는 IP3 Context Routing Engine v1.3의 첫 번째 고정 개발 순서인 Windows real telemetry 수집기와 Darwin/Linux/Windows strict validator, 그리고 claim guard CI 승격을 완성하기 위한 산출물입니다.

## 완료된 개발 항목

| 항목 | 상태 | 산출물 |
|---|---|---|
| evidence_class 체계 | 완료 | `evidence/evidence_class_taxonomy.json` |
| Windows collector 보강 | 완료 | `tools/collect_real_telemetry.py` |
| Windows gate 등급 분리 | 완료 | `tools/windows_real_telemetry_gate.py` |
| 3플랫폼 strict gate 등급 분리 | 완료 | `tools/all_platform_telemetry_gate.py` |
| claim guard 고도화 | 완료 | `tools/claim_guard.py` |
| GitHub Actions 3플랫폼 workflow | 완료 | `.github/workflows/ip3-v13-windows-telemetry-ci-lab.yml` |
| Windows VM runner | 완료 | `windows/collect_windows_telemetry_vm_lab.ps1` |
| Windows physical runner | 완료 | `windows/collect_windows_telemetry_physical_lab.ps1` |
| SEALED packaging gates | 완료 | `tools/clean_package_gate.py`, `tools/sha256_manifest.py`, `tools/seal_handoff.py` |
| AI 온디바이스13 인계 문서 | 완료 | 본 문서 |

## 아직 주장하지 않는 항목

- 실제 Windows 노트북 `PHYSICAL_LAB` 승인
- 운영 배포 또는 production release
- 실제 Butler 앱 production hook
- IP2 production PEP bridge
- IP1 v5.4 forward_verified=true
- Product Candidate full replay 완료

## CI_LAB 승격 절차

1. 레포에 패키지를 반영합니다.
2. GitHub Actions workflow를 실행합니다.
3. `collect-telemetry-ci-lab` job이 linux/darwin/windows telemetry를 수집합니다.
4. `seal-ci-lab-handoff` job이 artifact를 import하고 모든 gate를 실행합니다.
5. 성공 시 `evidence/sealed_handoff_ci_lab.json`에 `APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB`이 기록됩니다.

## 운영 배포와의 차이

CI_LAB은 CI runner에서 생성된 실제 runtime telemetry입니다. 그러나 대표 보유 장치, 고객 장치, 운영 앱, 운영 정책 서버, 운영 모델 bridge의 증빙은 아닙니다. production 승인은 별도 운영 증빙과 gate가 필요합니다.
