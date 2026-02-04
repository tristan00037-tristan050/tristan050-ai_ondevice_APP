# Web→App Core Porting Guide (QuickCheck / Policy / Gate / Bundle)

This guide describes how to lift the **web-core 4.17** operational rails into App Core.

## 1) Indicators (6)
- api, jwks, holidays, observability, ics, lighthouse (LH may be replaced with a light device metric if needed).

## 2) Policy Gate
- Validate policy JSON with `contracts/qc_policy.schema.json` (runtime guard required).
- Severity: `info|warn|block`. CI fails on `block` rules (and optionally `warn` with `--strict-warn`).

## 3) Report
- Markdown/JSON **order is fixed**: _Status → Diff → Policy → Notes_.  
- JSON keys must be: `status, diff, policy, notes, raw` (see `contracts/qc_report.schema.json`).

## 4) Redaction
- Use `redact_rules.example.json` as the base and **load rules at runtime**.  
- Guard against over-redaction (≥80%).

## 5) Bundle
- Produce `qc.md`, `qc.json`, `bundle_meta.json`, `checksums.txt` and optionally `*.zip`.  
- Include `base_url`, `policy_version`, `generated_at`, `app_core_version` in `bundle_meta.json`.

## 6) Standards (MUST)
- Labels: `decision|ok` only.  
- Internal gateway only; no `/ops` exposure from App.  
- ETag/TTL/JWKS/412 flows mirrored from web-core.

## 7) DoD
- App HUD/Reporter shows 6 indicators; Copy MD / Download JSON / Snapshot(#aqc) work.  
- Policy validated; Gate fails on block.  
- Redaction rules applied; no secrets/hosts leaked in PR/MD.
