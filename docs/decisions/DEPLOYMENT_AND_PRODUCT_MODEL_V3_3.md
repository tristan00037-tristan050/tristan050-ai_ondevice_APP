# Deployment & Product Model Decision — v3.3 (SSOT)

Date: 2026-01-26  
Status: DECIDED (ALL TEAMS: YES)  
Scope: Web/App/On-Prem Gateway / Mock-Live / Export / meta-only / P95 Budget

---

## 1) Final SSOT Decision (9 lines)

1) Product model: **Hybrid (On-device first + On-prem gateway)**  
2) Server must never receive raw text. Server handles: policy/auth, audit(meta-only), internal integrations, artifact versioning, device linking only.  
3) Web(PC): **Browser webapp (primary) + PWA (parallel)**. Electron is deferred (phase 2).  
4) Mobile: **Enterprise MDM distribution is default**.  
5) On-prem deployment: **Compose = phase 1 (Quickstart/PoC)**, **Helm/K8s = phase 2 (Enterprise GA)**. Helm chart skeleton (values schema/templates/version rules) is maintained from phase 1.  
6) Mock is default (network off). Live requires policy header bundle + meta-only allowlist; missing/violation is fail-closed.  
7) Export is always 2-step (Preview→Approve). Approve requires audit(meta-only). Preview/Approve display/send meta-only only. No raw text/excerpts allowed.  
8) Performance budget definition: **E2E P95 = "input done → 3-block render done"**.  
9) P95 contract/target: **contract ≤ 2.5s**, **target ≤ 2.0s**. Contract breach is regression-blocking gate in CI. Baseline environment is pinned (see below).

---

## 2) Mandatory clauses (4) — must be enforced by code/verify

A) Live policy header bundle must be validated (missing/tamper → fail-closed).  
B) meta-only allowlist is defined by a single schema file and enforced by the same validator on client/server (violation → store 0 + fail-closed).  
C) Export Approve must write audit_event_v2 (meta-only). Preview/Approve meta-only only.  
D) On-prem delivery must be "signed release bundle + install/verify runbook" (Compose/Helm common).

---

## 3) Agent policy (conflict A resolved)

Agent is not mandated in phase 1.  
Instead, we pin "agent trigger SSOT". If any trigger becomes mandatory in product track, start agent track immediately (Windows/macOS first).

Agent Trigger SSOT (minimum):
- Always-on local filesystem access (folder/path automation, watcher)
- Background residency (offline cache, job queue, scheduled runs)
- Local keystore / device identity binding (as feasible)
- Service-style artifact/runtime update separated from app
- OS integration beyond browser sandbox (DLP/clipboard/print controls, etc.)

---

## 4) P95 baseline environment (pinned)

**Baseline environment (single standard):** One company standard laptop class (e.g., i5/16GB-level or equivalent).

- Baseline PC: "one company standard laptop class (e.g., i5/16GB-level or equivalent)"
- Browser: Chrome latest
- Mode: Mock (network off)
- Scenario: one standard butler request producing 3 blocks (no raw text export)
- Measurement definition: "input done → 3-block render done"

---

## 5) Execution plan (PR queue)

PR-PROD-01: This SSOT decision doc (current PR)  
PR-PROD-02: Policy header bundle fail-closed + reason_code tests + verify  
PR-PROD-03: meta-only allowlist single schema + shared validator + deny/audit  
PR-PROD-04: Export 2-step + Approve audit_event_v2 (meta-only)  
PR-PROD-05: Mock network 0 hard gate + tests  
PR-PERF-01: P95 harness + baseline + regression blocking gate  
On-prem parallel: PR-ONPREM-01 (Compose Quickstart), PR-ONPREM-02 (Helm skeleton)

