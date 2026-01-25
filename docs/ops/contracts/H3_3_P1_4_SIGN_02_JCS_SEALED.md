# Hardening++ / Milestone 3.3 — P1-4 SIGN-02 (SEALED)

## Result
- RFC 8785(JCS) canonicalizer single source pinned (prevents drift).
- Golden vectors added.
- Repo-guards blocks duplicate JCS/canonicalize implementations (fail-closed).

## Code PR
- PR: <fill after merge>

## Evidence (how to verify)
- PR → Checks: repo-guards must be Success (green)
- Local DoD:
  - bash scripts/verify/verify_jcs_single_source.sh ; echo EXIT=$?
    - CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1 and EXIT=0

