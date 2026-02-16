# TASK QUEUE POLICY — v1 (SSOT)

Date: 2026-02-16
Status: DECIDED
Scope: Task queue idempotency, concurrency safety, atomic writes (fail-closed)

## Goal

Task queue escape = 0 by construction. Idempotent execution, concurrency-safe, no partial writes.

## Invariants (must be enforced by code)

1) Idempotency: Same task_id executed multiple times produces identical result.
2) Concurrency: Concurrent execution of same task_id is safe (no race conditions).
3) Partial write = 0: Write operations are atomic (all-or-nothing, no partial state).

## Implementation SSOT

- Policy: `docs/ops/contracts/TASK_QUEUE_POLICY_V1.md`
- Library: `scripts/agent/task_queue_v1.cjs`
- Self-test: `scripts/agent/task_queue_selftest_v1.cjs`
- Verify gate: `scripts/verify/verify_task_queue_v1.sh`
- Repo-wide gate wiring: `scripts/verify/verify_repo_contracts.sh`

## DoD Keys (printed by verify only)

- TASK_QUEUE_IDEMPOTENCY_OK=1
- TASK_QUEUE_CONCURRENCY_OK=1
- TASK_QUEUE_PARTIAL_WRITE_0_OK=1

## Token

TASK_QUEUE_POLICY_V1_TOKEN=1

