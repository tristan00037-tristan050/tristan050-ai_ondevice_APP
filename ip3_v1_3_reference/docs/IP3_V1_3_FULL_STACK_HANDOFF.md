# IP3 v1.3 Full-Stack Handoff

## 목적

본 산출물은 IP #3 On-device Context Routing Engine을 v1.3 수준으로 고도화하기 위한 코드/테스트/증빙/게이트 패키지입니다. 개발지시서의 Subphase 3.0~3.8을 모두 코드 구조와 게이트에 반영하되, 실제 Windows 물리 장치, 실제 Butler 앱 배포, IP #2 live PEP, IP #1 v5.4 forward evidence가 없으면 높은 등급 claim을 차단합니다.

## 개발지시서 반영표

| Subphase | 구현 | 게이트 |
|---|---|---|
| 3.0 Schema Lockdown | `schema/ip3_routing_contract.schema.json`, routing enum | `tools/routing_schema_gate.py` |
| 3.0A Threat Model | threat/failure taxonomy | `tools/threat_model_gate.py`, `tools/claim_guard.py` |
| 3.1 5중 측정 | CPU/RAM/battery/thermal/network telemetry | `tools/collect_real_telemetry.py`, telemetry gates |
| 3.2 장치 등급 | A/B/C/D classifier | unit tests |
| 3.3 UserContext | 4축 점수, request digest | unit tests, raw content scan |
| 3.4 4단 routing | policy -> executable -> capacity -> target | `tools/live_app_hook_replay.py` |
| 3.5 routing hook | ButlerAppSourceRoutingHook harness | `tools/live_app_hook_replay.py` |
| 3.6 audit | digest-only hash chain | replay evidence |
| 3.7 fail-safe | 6 injection scenarios | `tools/failsafe_live_injection_gate.py` |
| 3.8 adaptive profile | digest-only profile update | unit tests |

## 승인 경계

현재 패키지는 `FULL_STACK_LOCAL_DEVELOPMENT_AND_CI_LAB_SEALABLE_CANDIDATE`입니다. 운영 완료본이 아니며 production claim은 차단됩니다.
