#!/usr/bin/env bash
set -euo pipefail

# P23-P2-03: gen_bundle_graph_lock_v1.sh
# BUNDLE_GRAPH_LOCK_V1.json의 artifact_digest_sha256 필드를 실제 파일 해시로 채움.
# lock_digest_sha256는 lock_digest_sha256 키 제외 후 자기 자신 해시로 계산.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

LOCK_FILE="docs/ops/contracts/BUNDLE_GRAPH_LOCK_V1.json"
[[ -f "$LOCK_FILE" ]] || { echo "ERROR_CODE=BUNDLE_GRAPH_LOCK_MISSING"; echo "HIT_PATH=$LOCK_FILE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$LOCK_FILE" <<'PYEOF'
import json, sys, os, hashlib, datetime, subprocess

lock_path = sys.argv[1]

with open(lock_path, encoding='utf-8') as f:
    lock = json.load(f)

root = subprocess.check_output(
    ['git', 'rev-parse', '--show-toplevel'],
    text=True
).strip()

errors = []
for node in lock.get("nodes", []):
    artifact_path = os.path.join(root, node["artifact_path"])
    if os.path.isfile(artifact_path):
        with open(artifact_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        node["artifact_digest_sha256"] = digest
    else:
        errors.append(f"ARTIFACT_MISSING:{node['artifact_path']}")

if errors:
    for e in errors:
        print(f"ERROR_CODE={e}")
    sys.exit(1)

lock["generated_at_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
lock["status"] = "generated"

# Compute self-referencing lock_digest (exclude lock_digest_sha256 key)
lock_without_digest = {k: v for k, v in lock.items() if k != "lock_digest_sha256"}
canonical = json.dumps(lock_without_digest, sort_keys=True, ensure_ascii=False)
lock_digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
lock["lock_digest_sha256"] = lock_digest

with open(lock_path, 'w', encoding='utf-8') as f:
    json.dump(lock, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"OUTPUT={lock_path}")
print(f"LOCK_DIGEST={lock_digest}")
PYEOF
