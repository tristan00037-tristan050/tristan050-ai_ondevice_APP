# A4 v5.6 — Cross-branch secret-scan notice (not on this PR)

The full-repository audit (`a4_repository_secret_scan.py --history-scope all`)
surfaced one `GENERIC_BEARER` candidate that is **not reachable from PR #867's
head** and is therefore out of scope for the PR merge gate (which scans
`--history-scope head`). It is recorded here so the owning branch/team can
triage it. No secret value is reproduced in this file.

## Finding
- Rule: `GENERIC_BEARER`
- Git blob object: `7d95fb1afe05593f3fa8be06719830c790c640b6`
- Path: `butler-desktop/src/__tests__/SidecarFetchSecurity.test.ts` (line 24)
- Path digest: `180dc1d3b2aaaa5e4d0cd0d28da76c7b637f627ea8860316975cbad6aca43d35`
- Owning branch (only ref that reaches this blob): `origin/pr/firstscreen-v2.7-final-correction`
- Reachable from `feat/box5-a4-v5-4-single-integration` (PR #867): **no**

## Assessment: synthetic test fixture (not a live credential)
`SidecarFetchSecurity.test.ts` is a Vitest unit test. It mocks the capability
token with `vi.fn().mockResolvedValue(...)` to a self-describing literal whose
prefix is `test-` (21 characters), and line 24 asserts that the outgoing
`Authorization` header equals that same mocked value. The flagged value is that
hardcoded test literal, matching the mock on line 4 — not a real secret. (The
raw value is intentionally not reproduced here so this notice does not itself
trip the scanner.)

## Recommended action (for the owning branch/team)
- Confirm the assessment above on `pr/firstscreen-v2.7-final-correction`.
- Optional hygiene on that branch (not this PR): replace the literal with an
  obviously-fake value or otherwise make the test's intent unmistakable so the
  repo-wide audit stops flagging it.
- **Do not** add this to `A4_V55_SECRET_SCAN_BASELINE.json`. Per 문제점검7 P1 the
  baseline is pinned to the protected approval manifest; suppressions must be
  audited and manifest-approved, and cross-branch fixtures should be fixed on
  their own branch rather than baselined into an unrelated PR.
- **If** the owning team determines this is or ever was a real credential, rotate
  it regardless of scope and record rotation evidence, exactly as done for the
  `.env.backup` exposure in PR #867.
