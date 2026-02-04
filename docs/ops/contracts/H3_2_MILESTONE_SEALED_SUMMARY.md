# Hardening++ / Milestone 3.2 — SEALED Summary (SSOT)

Status: SEALED (P0-1..P0-4, P1-1..P1-3 all merged + records pinned)

## Core invariants sealed
- tests/source contamination: OK=1 or *_OK=1 injection forbidden (verify output only)
- PASS(exit 0) only emits *_OK=1; FAIL keeps *_OK=0 and exits non-zero (fail-closed)
- Ops deps preflight standardized; rg consistency enforced in product-verify workflows
- Sentence/log grep verdict forbidden (machine-verdict only, Jest JSON where applicable)
- npm ci only: verify scripts must not use npm install fallback (repo-guards blocks regressions)

## PRs (merged)
P0 line
- P0-1 GUARD (Required checks: name stability + no skipped bypass)
  - PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/195
  - merge_commit_sha: ba340a0eedac9a06b91913bc1298c92fe15b4d51
  - merged_at: 2026-01-24T04:22:50Z

- P0-2 AUDIT (audit_event_v2 + force action auditing)
  - PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/196
  - merge_commit_sha: 1e428950bd922bc7812d7863173b34cc8add8205
  - merged_at: 2026-01-24T04:36:03Z

- P0-3 METRICS (24h counters single-writer + idempotent event_id)
  - PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/197
  - merge_commit_sha: fd47446a93b0a27bbdbd95dbe05ceb72cdc36d08
  - merged_at: 2026-01-24T04:48:38Z

- P0-4 OPS-DEPS (deps preflight + rg install standardization + npm ci only enforcement)
  - Code PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/198
  - merge_commit_sha: 25ca98e34de2cb9f301ede86ee945d1caf4b632b
  - merged_at: 2026-01-24T05:26:59Z
  - Record PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/199
  - record_merge_commit_sha: 590f06a71528239ad1390968155644e6dc79bacf
  - record_merged_at: 2026-01-24T05:43:42Z
  - Evidence run: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/21309926711

P1 line
- P1-1 SVR-05 attestation verdict: log-grep removed, Jest JSON machine-verdict
  - Code PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/200
  - merge_commit_sha: 3146b5ad9c866c512b70d3ee97592374ff07e33f
  - Record PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/201
  - record_merge_commit_sha: 82fdfdd72180d17ffc66c9319134ce21211b6690
  - record_merged_at: 2026-01-24T06:23:50Z

- P1-2 Repo-guards: forbid log-grep verdict regressions
  - Code PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/202
  - merge_commit_sha: a5103b56a229803b7af3a323ee3f93599da3d6db
  - merged_at: 2026-01-24T06:40:21Z
  - Record PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/203
  - record_merge_commit_sha: 081d1bc4d4ea3eb65d48d93b708a6a694d646973
  - record_merged_at: 2026-01-24T06:45:30Z

- P1-3 Repo-guards: forbid npm install fallback regressions (npm ci only)
  - Code PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/204
  - merge_commit_sha: ccfc6391a8938f2c5ba5a78832b685280367ebb5
  - merged_at: 2026-01-25T00:49:16Z
  - Record PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/205
  - record_merge_commit_sha: f6acdffc5f85d987a3ffa1add960f40ebe30e752
  - record_merged_at: 2026-01-25T00:54:13Z

## Record files (in-repo)
- docs/ops/contracts/H3_2_P0_4_OPS_DEPS_01_SEALED.md
- docs/ops/contracts/H3_2_P1_1_ATTESTATION_JEST_JSON_SEALED.md
- docs/ops/contracts/H3_2_P1_2_FORBID_LOG_GREP_VERDICT_SEALED.md
- docs/ops/contracts/H3_2_P1_3_FORBID_NPM_INSTALL_FALLBACK_SEALED.md
