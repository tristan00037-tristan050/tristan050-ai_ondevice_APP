#!/usr/bin/env bash
set -euo pipefail

# P23-P2-04: verify_merkle_artifact_tree_v1.sh
# tools/supply-chain/merkle_v1.ts 존재 및 필수 심볼 검증.
# TypeScript 심볼: buildMerkleTree, getMerkleRoot, verifyMerkleLeaf, hashLeaf, hashNode

MERKLE_ARTIFACT_TREE_V1_OK=0
trap 'echo "MERKLE_ARTIFACT_TREE_V1_OK=${MERKLE_ARTIFACT_TREE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TS_FILE="tools/supply-chain/merkle_v1.ts"

set +e
python3 - "$TS_FILE" <<'PYEOF'
import sys, os

ts_path = sys.argv[1]

if not os.path.isfile(ts_path):
    print(f"ERROR_CODE=MERKLE_TS_MISSING")
    print(f"HIT_PATH={ts_path}")
    sys.exit(1)

ts_src = open(ts_path, encoding='utf-8').read()

required_symbols = [
    "buildMerkleTree",
    "getMerkleRoot",
    "verifyMerkleLeaf",
    "hashLeaf",
    "hashNode",
    "MerkleLeaf",
    "MerkleNode",
    "MerkleTree",
    "MERKLE_EMPTY_LEAVES",
    "typedDigest",
    "merkle-leaf",
    "merkle-node",
]
for sym in required_symbols:
    if sym not in ts_src:
        print(f"ERROR_CODE=MERKLE_TS_SYMBOL_MISSING:{sym}")
        sys.exit(1)

# Verify domain tag usage (leaf and node must use different tags)
if "merkle-leaf" not in ts_src or "merkle-node" not in ts_src:
    print("ERROR_CODE=MERKLE_DOMAIN_TAGS_MISSING")
    sys.exit(1)

# Verify duplicate-last-leaf padding comment
if "duplicate" not in ts_src.lower() and "padding" not in ts_src.lower():
    print("ERROR_CODE=MERKLE_ODD_LEAF_HANDLING_UNDOCUMENTED")
    sys.exit(1)

print("STATUS=ok")
print("MERKLE_ARTIFACT_TREE_V1=OK")
PYEOF
py_rc=$?
set -e

if [ $py_rc -ne 0 ]; then
  exit 1
fi

MERKLE_ARTIFACT_TREE_V1_OK=1
exit 0
