# On-Prem Self-Proof Roadmap

STATUS=PENDING_REAL_SELF_PROOF_HARNESS

온프렘 자가증명(real on-prem self-proof harness)은 아직 구현 완료 상태가 아니다.

현재 `ONPREM_REAL_WORLD_PROOF_LATEST.md`는 최신 성공 마커를 보관하지만, 날짜만 갱신하는 방식으로 freshness를 통과시키는 것은 허용하지 않는다. freshness 검사는 `ONPREM_PROOF_FRESHNESS_ENFORCE=1`일 때만 차단 가드로 동작하며, 기본 PR/merge_group 경로에서는 stale 상태를 `ONPREM_PROOF_LATEST_FRESH_SKIPPED=1`로 보고한다.

재활성 조건:

1. 실제 온프렘 self-proof harness가 구현된다.
2. harness가 proof를 직접 재실행하고 `git_sha`, `ts_utc`, exit code, egress-deny 관측값을 갱신한다.
3. 날짜-only bump 도구 없이 재현 가능한 증거가 생성된다.
4. 검증 완료 후 `ONPREM_PROOF_FRESHNESS_ENFORCE=1`로 freshness 차단을 다시 켠다.
