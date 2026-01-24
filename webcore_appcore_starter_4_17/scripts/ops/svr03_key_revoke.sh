#!/usr/bin/env bash
set -euo pipefail

# Ops script: NO *_OK=1 output
# Usage: bash .../svr03_key_revoke.sh --key_id k1 --reason_code KEY_REVOKED

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

KEY_ID=""
REASON_CODE="KEY_REVOKED"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key_id) KEY_ID="${2:-}"; shift 2;;
    --reason_code) REASON_CODE="${2:-}"; shift 2;;
    *) echo "FAIL: unknown arg $1"; exit 2;;
  esac
done

[[ -n "$KEY_ID" ]] || { echo "FAIL: --key_id required"; exit 1; }

# 실제 revoke는 key_store 구현/운영 방식에 맞춰 연결해야 함.
# 여기서는 감사 이벤트만 봉인(강제 행위 감사 가능성)하고, revoke 연결은 후속 PR에서 실제 운영 경로로 확정 가능.
cd "$ROOT/backend/model_registry"
KEY_ID="$KEY_ID" REASON_CODE="$REASON_CODE" REPO_SHA="${REPO_SHA:-unknown}" node - <<'NODE'
const { appendAuditV2, hashActorId, newEventId, nowUtcIso } = require("./services/audit_append");
const repoSha = process.env.REPO_SHA || "unknown";

const keyId = process.env.KEY_ID;
const rc = process.env.REASON_CODE;

appendAuditV2({
  v: 2,
  ts_utc: nowUtcIso(),
  event_id: newEventId("KEY_REVOKE"),
  actor_type: "human",
  actor_id_hash: hashActorId(process.env.USER || "unknown"),
  action: "KEY_REVOKE",
  reason_code: rc,
  repo_sha: repoSha,
  target: { key_id: keyId },
  outcome: "ALLOW",
  policy_version: "h3.2",
});
NODE

