# WEB-UX-01 Mode Switch E2E — SEALED Record

Purpose: pin WEB-UX-01 verification method as output-based evidence to prevent re-litigation.

Evidence (how to verify)
1) Repo-guards (assets gate)
- Command:
  - bash scripts/verify/verify_repo_contracts.sh ; echo EXIT=$?
- Expect:
  - WEB_E2E_MODE_SWITCH_WIRED_OK=1
  - WEB_E2E_MOCK_NETWORK_ZERO_OK=1
  - WEB_E2E_LIVE_HEADER_BUNDLE_OK=1
  - EXIT=0

2) Full local E2E (real browser run)
- Command:
  - bash webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_01_mode_switch_e2e.sh ; echo EXIT=$?
- Expect:
  - WEB_E2E_MODE_SWITCH_WIRED_OK=1
  - WEB_E2E_MOCK_NETWORK_ZERO_OK=1
  - WEB_E2E_LIVE_HEADER_BUNDLE_OK=1
  - EXIT=0

Notes
- package-lock.json is mandatory (npm ci only); missing lockfile must fail-closed.
