# FirstScreen v2.3 요구사항 추적

| 요구 | 상태 | 정본 |
|---|---|---|
| FS22-P0-001 자기해시 제거·Ed25519 검증 | LOCAL_PASS, OWNER_SIGNATURE_PENDING | `verify_storage_risk_acceptance.py`; v2.3 schema; attack tests |
| FS22-P0-002 제목·FTS 위험 승인 | BLOCKED_OWNER_UNSIGNED | `release_exceptions/` |
| FS22-P0-003 no-git SBOM | LOCAL_PASS | `generate_cyclonedx_sbom.py`; `test_release_sbom.py` |
| FS22-P0-004 archive bytes 결속·safe extract | LOCAL_PASS | `verify_source_bundle.py`; archive attack tests |
| policy guard와 generated dist 충돌 | LOCAL_PASS_SOURCE_LEVEL | `verify_policy_headers_source.py` |
| FS22-P0-005 저장소 기존 실패 소유 분리 | TRACKED_NOT_CLOSED | `REPOSITORY_FAILURE_OWNERS.md` |
| FS22-P0-006 critical branch 85% | FAIL_LOCAL | coverage gate |
| FS22-P0-007 remote/PR/hosted attestation | NOT_RUN | 외부 canonical repository 필요 |
| FS22-P0-008 signed macOS/Keychain | NOT_RUN | macOS 15 arm64 실기기 필요 |
| FS22-P0-009 Playwright/axe/VoiceOver | NOT_RUN | browser·signed app 실측 필요 |
| FS22-P1-010 archive payload byte compare | LOCAL_PASS | direct ZIP entry digest/blob verification |
| FS22-P1-011 duplicate/order/mode/type/size defense | LOCAL_PASS | source verifier |
| FS22-P1-012 Idempotency CORS expose | LOCAL_PASS | actual sidecar middleware contract test |
| FS22-P1-013 Tauri write least privilege | CODE_PASS_LOCAL_WEB; MACOS_COMPILE_NOT_RUN | native `save_export_file`; capability |
| FS22-P1-021 monolith 분해 | PARTIAL | native export authority와 verifier 책임 분리; HomeStore/App/sidecar 잔여 |
| accounting_review 변경 금지 | PASS_LOCAL | baseline diff gate |
| runtime activation | 0 | 별도 운영 승인 전 불변 |
