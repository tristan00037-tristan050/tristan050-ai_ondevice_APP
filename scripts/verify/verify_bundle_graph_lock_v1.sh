#!/usr/bin/env bash
set -euo pipefail

# P23-P2-03: verify_bundle_graph_lock_v1.sh
# BUNDLE_GRAPH_LOCK_V1.json 존재, 필드, DAG 순환 없음 검증.
# status=pending_real_weights → ENFORCE=0 → SKIPPED=1

BUNDLE_GRAPH_LOCK_V1_OK=0
trap 'echo "BUNDLE_GRAPH_LOCK_V1_OK=${BUNDLE_GRAPH_LOCK_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

LOCK_FILE="docs/ops/contracts/BUNDLE_GRAPH_LOCK_V1.json"
ENFORCE="${ENFORCE:-0}"

set +e
python3 - "$LOCK_FILE" "$ENFORCE" <<'PYEOF'
import json, sys, os

lock_path, enforce = sys.argv[1], sys.argv[2]

if not os.path.isfile(lock_path):
    print(f"ERROR_CODE=BUNDLE_GRAPH_LOCK_MISSING")
    print(f"HIT_PATH={lock_path}")
    sys.exit(1)

with open(lock_path, encoding='utf-8') as f:
    lock = json.load(f)

required_fields = ["schema_version", "lock_id", "nodes", "lock_digest_sha256", "status"]
for field in required_fields:
    if field not in lock:
        print(f"ERROR_CODE=LOCK_FIELD_MISSING:{field}")
        sys.exit(1)

status = lock.get("status", "")

if status == "pending_real_weights" or status == "PLACEHOLDER" or lock.get("lock_digest_sha256") == "PLACEHOLDER":
    if enforce == "0":
        print("STATUS=pending")
        print("SKIPPED=1")
        sys.exit(2)
    else:
        print("ERROR_CODE=BUNDLE_GRAPH_LOCK_PENDING_ENFORCE=1")
        sys.exit(1)

# Validate nodes
nodes = lock.get("nodes", [])
if not nodes:
    print("ERROR_CODE=BUNDLE_GRAPH_LOCK_EMPTY_NODES")
    sys.exit(1)

node_ids = set()
for node in nodes:
    for f in ["node_id", "artifact_path", "artifact_digest_sha256", "depends_on"]:
        if f not in node:
            print(f"ERROR_CODE=NODE_FIELD_MISSING:{f} in {node.get('node_id','?')}")
            sys.exit(1)
    if node["artifact_digest_sha256"] in ("REQUIRED", "PLACEHOLDER", ""):
        print(f"ERROR_CODE=NODE_DIGEST_PLACEHOLDER:{node['node_id']}")
        sys.exit(1)
    if len(node["artifact_digest_sha256"]) != 64:
        print(f"ERROR_CODE=NODE_DIGEST_INVALID_LENGTH:{node['node_id']}")
        sys.exit(1)
    node_ids.add(node["node_id"])

# Check all depends_on references are valid node_ids
for node in nodes:
    for dep in node.get("depends_on", []):
        if dep not in node_ids:
            print(f"ERROR_CODE=DANGLING_DEPENDENCY:{node['node_id']} depends on unknown {dep}")
            sys.exit(1)

# Cycle detection (DFS)
adj = {node["node_id"]: node["depends_on"] for node in nodes}
def has_cycle(node_id, visited, stack):
    visited.add(node_id)
    stack.add(node_id)
    for dep in adj.get(node_id, []):
        if dep not in visited:
            if has_cycle(dep, visited, stack):
                return True
        elif dep in stack:
            return True
    stack.discard(node_id)
    return False

visited, stack = set(), set()
for node_id in node_ids:
    if node_id not in visited:
        if has_cycle(node_id, visited, stack):
            print(f"ERROR_CODE=BUNDLE_GRAPH_CYCLE_DETECTED")
            sys.exit(1)

# lock_digest_sha256 self-check
import hashlib
lock_without_digest = {k: v for k, v in lock.items() if k != "lock_digest_sha256"}
canonical = json.dumps(lock_without_digest, sort_keys=True, ensure_ascii=False)
expected_digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
if lock["lock_digest_sha256"] != expected_digest:
    print(f"ERROR_CODE=LOCK_DIGEST_MISMATCH")
    print(f"EXPECTED={expected_digest}")
    print(f"ACTUAL={lock['lock_digest_sha256']}")
    sys.exit(1)

print("STATUS=ok")
print("BUNDLE_GRAPH_LOCK_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -eq 2 ]; then
  echo "BUNDLE_GRAPH_LOCK_V1_SKIPPED=1"
  BUNDLE_GRAPH_LOCK_V1_OK=1
  exit 0
elif [ $py_rc -ne 0 ]; then
  exit 1
fi

BUNDLE_GRAPH_LOCK_V1_OK=1
exit 0
