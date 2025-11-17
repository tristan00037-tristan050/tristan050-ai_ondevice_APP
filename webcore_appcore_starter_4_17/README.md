# Web→App Core Starter Bundle (Baseline: web-core 4.17)

This bundle packages **shared contracts and operational conventions** so that an **App Core** project
can reuse the QuickCheck/Policy/Gate/Redaction/Bundle pipeline that was hardened in web-core 4.17.

## What’s inside
- **contracts/**
  - `qc_policy.schema.json` — JSON Schema for QuickCheck policy (with `policy_version`, `created_at`, `rules[].severity`).
  - `qc_report.schema.json` — JSON Schema for QuickCheck JSON export (`status → diff → policy → notes → raw`).
  - `redact_rules.schema.json` — JSON Schema for PR comment redaction rules.
- **configs/**
  - `webcore_qc_policy.example.json` — Example policy aligned to web-core 4.17 (severity: info|warn|block).
- **redact/**
  - `redact_rules.example.json` — Default masking rules (tokens, internal hosts, IPs) + notes on 80% over-redaction guard.
- **scripts/ops/**
  - `app_quickcheck_md.mjs` — Node script to format a QuickCheck JSON snapshot as Markdown (App-side).
  - `app_quickcheck_gate.mjs` — Policy Gate evaluator on top of a QuickCheck JSON + policy JSON.
  - `app_quickcheck_bundle.mjs` — Create bundle with `qc.md`, `qc.json`, `bundle_meta.json`, `checksums.txt` and optional zip.
- **docs/**
  - `WEBCORE_TO_APPCORE_PORTING.md` — How to wire App Core to the same operational rails.
- **checklists/**
  - `OneMinuteChecklist.md` — Pre-flight checks for App Core QuickCheck/Gate.
- **examples/**
  - `qc_snapshot.example.json` — Example QuickCheck snapshot for local testing of formatter and gate.
- **metadata/**
  - `VERSION` — Source baseline (web-core-4.17.0).

## Shared standards (MUST)
- **Metric labels**: `decision|ok` only (whitelist). No other labels allowed.
- **Targets**: Calls must hit **internal gateway** only; **no /ops exposure** from App.
- **Policy Gate**: only `severity=block` rules fail CI; `warn` can optionally fail with `--strict-warn` mode.
- **Report order**: `Status → Diff → Policy → Notes`, keys in JSON export must be `status, diff, policy, notes, raw`.
- **A11y/Perf**: reduced motion honored; deltas with EPS(1e-6) guard and ±500% clamp.
