# Helper1 v2 product boundary

This file defines claims that the current source tree is allowed to make.

## Connected runtime path

`butler_sidecar.py` calls `initialize_helper1_product()` during application
startup. The composition root accepts only the packaged native extension and
registers a pipeline together with its production execution authority. The ask
and search routes remain unavailable when this assembly cannot prove its native
assets, index generation, release identity, and capability session.

The Desktop accepts an answered result only after the Tauri command supplies a
release-bound trust anchor and WebCrypto verifies the Ed25519 execution receipt
against the request, session, workspace, generation, action, answer digest,
expiry, and replay cache. Refusal results do not require a trust anchor and stay
usable while production activation is blocked.

## Explicitly excluded claims

- The repository does not currently expose Helper1 document ingestion as a
  product route. Parser unit tests are not evidence of macOS App Sandbox
  enforcement.
- The protected trust policy is disabled until an independent owner pins the
  producer identity and both public keys on the protected default branch.
- No approved production asset closure, native model/index-loader receipt,
  Apple-silicon hardware measurement, or remote required-check result is
  present in this source tree. The source declares the fixed subject check
  `helper1-v2-protected-subject-verdict`, but it has no merge-blocking authority
  until the protected workflow is on the default branch and the remote ruleset
  requires that exact context from the GitHub Actions app.

Therefore `CODE_PASS`, product release, runtime activation, production claims,
and external handoff all remain denied. These values may change only through
the protected verifier after every required evidence class is independently
validated.

## Status (2026-08-06)

The protected-evidence bootstrap cycle (FSQ61-NEXT-P0-01) is closed on this
branch: the PR producer uploads untrusted raw materials, and the six evidence
lanes report PASSED except the native macOS lane, which stays BLOCKED with
`MACOS_NATIVE_LANE_NOT_CONFIGURED` (self-hosted runner infrastructure, tracked
separately). The trust policy remains `enabled: false`.
