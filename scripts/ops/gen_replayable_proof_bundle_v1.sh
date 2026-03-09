#!/usr/bin/env bash
set -euo pipefail

# P23-P2-05: gen_replayable_proof_bundle_v1.sh
# REPLAYABLE_PROOF_BUNDLE_V1.json의 component digest를 실제 파일 해시로 채우고
# merkle_root_digest 및 bundle_digest_sha256 계산.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BUNDLE_FILE="docs/ops/contracts/REPLAYABLE_PROOF_BUNDLE_V1.json"
[[ -f "$BUNDLE_FILE" ]] || { echo "ERROR_CODE=REPLAYABLE_PROOF_BUNDLE_MISSING"; echo "HIT_PATH=$BUNDLE_FILE"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

"$PYTHON_BIN" - "$BUNDLE_FILE" "$ROOT" <<'PYEOF'
import json, sys, os, hashlib, datetime

bundle_path, root = sys.argv[1], sys.argv[2]

with open(bundle_path, encoding='utf-8') as f:
    bundle = json.load(f)

errors = []
leaves = []

for component_id, component in bundle.get("components", {}).items():
    artifact_path = os.path.join(root, component["source"])
    if os.path.isfile(artifact_path):
        with open(artifact_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        component["digest_sha256"] = digest
        leaves.append({"artifact_id": component_id, "artifact_digest_sha256": digest})
    else:
        errors.append(f"COMPONENT_ARTIFACT_MISSING:{component['source']}")

if errors:
    for e in errors:
        print(f"ERROR_CODE={e}")
    sys.exit(1)

# Build Merkle tree — mirrors merkle_v1.ts typedDigest() with JCS canonicalization
def jcs_canonicalize(obj):
    """RFC 8785 JCS compatible canonical JSON — matches TS canonicalStringify()"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    if isinstance(obj, list):
        return '[' + ','.join(jcs_canonicalize(v) for v in obj) + ']'
    # dict: sort keys
    parts = []
    for k in sorted(obj.keys()):
        parts.append(
            json.dumps(k, ensure_ascii=False, separators=(',', ':'))
            + ':'
            + jcs_canonicalize(obj[k])
        )
    return '{' + ','.join(parts) + '}'

def typed_digest(domain_tag, schema_version, payload):
    envelope = {
        'domain_tag': domain_tag,
        'schema_version': schema_version,
        'payload': payload,
    }
    canonical = jcs_canonicalize(envelope)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def hash_leaf(leaf):
    return typed_digest("merkle-leaf", "v1", leaf)

def hash_node(left, right):
    return typed_digest("merkle-node", "v1", {"left_digest": left, "right_digest": right})

current_level = [hash_leaf(l) for l in leaves]
while len(current_level) > 1:
    next_level = []
    for i in range(0, len(current_level), 2):
        l = current_level[i]
        r = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
        next_level.append(hash_node(l, r))
    current_level = next_level

merkle_root = current_level[0] if current_level else ""
bundle["merkle_root_digest"] = merkle_root
bundle["generated_at_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
bundle["status"] = "generated"

# Self-referencing bundle_digest (exclude bundle_digest_sha256 key)
bundle_without_digest = {k: v for k, v in bundle.items() if k != "bundle_digest_sha256"}
canonical = json.dumps(bundle_without_digest, sort_keys=True, ensure_ascii=False)
bundle_digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
bundle["bundle_digest_sha256"] = bundle_digest

with open(bundle_path, 'w', encoding='utf-8') as f:
    json.dump(bundle, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"OUTPUT={bundle_path}")
print(f"MERKLE_ROOT={merkle_root}")
print(f"BUNDLE_DIGEST={bundle_digest}")
PYEOF
