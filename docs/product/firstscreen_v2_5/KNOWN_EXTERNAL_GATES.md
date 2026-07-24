# 외부 필수 게이트

다음 상태는 로컬 산출물로 대체할 수 없다.

- canonical remote, 최종 PR, clean clone, required CI: NOT_RUN
- protected CI bootstrap root와 2-of-3 offline root ceremony/recovery rehearsal: NOT_RUN
- owner risk-decision/revocation/release public artifacts와 threshold signature: BLOCKED_OWNER
- GitHub main artifact attestation과 별도 consumer signer/repository/workflow 검증: NOT_RUN
- Rust 1.97.1 macOS·Windows compile/clippy/unit: NOT_RUN
- Developer ID signed/notarized macOS 15 arm64 앱: NOT_RUN
- Keychain restart continuity·rollback·CAS·write-failure injection: NOT_RUN
- 실제 sidecar browser E2E, axe, keyboard, trace raw-zero: NOT_RUN
- VoiceOver label/role/order/announcement: NOT_RUN
- Windows existing-file atomic replace, CFA denial, sharing violation, crash recovery: NOT_RUN
- Apple M3 Metal, RSS, CPU, thermal, energy/power raw measurement: NOT_RUN
- 독립 프로세스·독립 검토팀 재현: NOT_RUN

이 항목 중 하나라도 누락되면 제품 출시 승인을 만들지 않는다.
