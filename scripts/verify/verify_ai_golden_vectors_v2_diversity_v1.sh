#!/usr/bin/env bash
set -euo pipefail

AI_GOLDEN_VECTORS_V2_DIVERSITY_OK=0
AI_GOLDEN_VECTORS_NO_RAW_OK=0

trap 'echo "AI_GOLDEN_VECTORS_V2_DIVERSITY_OK=${AI_GOLDEN_VECTORS_V2_DIVERSITY_OK}";
      echo "AI_GOLDEN_VECTORS_NO_RAW_OK=${AI_GOLDEN_VECTORS_NO_RAW_OK}"' EXIT

gv="scripts/ai/golden_vectors_v2.json"
test -f "$gv" || { echo "BLOCK: missing $gv"; exit 1; }

# raw_text family must not exist as JSON keys (key-syntax only)
if grep -EIn '"raw_text"[[:space:]]*:|"rawText"[[:space:]]*:|"raw_texts"[[:space:]]*:|"rawTexts"[[:space:]]*:' "$gv" >/dev/null 2>&1; then
  echo "BLOCK: forbidden raw_text* key present in golden_vectors_v2.json"
  exit 1
fi

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "BLOCK: python3/python not found"; exit 1; }

"$PYTHON_BIN" - <<'PY'
import json, sys
p="scripts/ai/golden_vectors_v2.json"
d=json.load(open(p,"r",encoding="utf-8"))

# normalize list
if isinstance(d,list):
  items=d
elif isinstance(d,dict):
  for k in ("vectors","cases","items","data"):
    if k in d and isinstance(d[k],list):
      items=d[k]; break
  else:
    items=[d]
else:
  print("BLOCK: unexpected root"); sys.exit(1)

# Minimum N
N_MIN=10
if len(items) < N_MIN:
  print(f"BLOCK: need at least {N_MIN} vectors, got {len(items)}")
  sys.exit(1)

# feature_digest_v1 must exist and be dict
dcs=set(); modes=set(); polys=set(); vers=set()
for i,it in enumerate(items):
  if not isinstance(it,dict):
    print("BLOCK: vector must be object"); sys.exit(1)
  fd=it.get("feature_digest_v1")
  if not isinstance(fd,dict):
    print(f"BLOCK: missing feature_digest_v1 at index {i}")
    sys.exit(1)
  # required ids
  if "model_pack_id" not in fd or "pack_version_id" not in fd:
    print(f"BLOCK: digest missing model_pack_id/pack_version_id at index {i}")
    sys.exit(1)
  vers.add(str(fd.get("pack_version_id")))
  dcs.add(str(fd.get("device_class_id","")))
  modes.add(str(fd.get("mode","")))
  polys.add(str(fd.get("policy_id","")))

# Diversity heuristics (fail-closed but realistic)
# - at least 3 device classes
# - at least 2 modes
# - at least 2 policies
if len([x for x in dcs if x]) < 3:
  print(f"BLOCK: device_class_id diversity too low: {dcs}")
  sys.exit(1)
if len([x for x in modes if x]) < 2:
  print(f"BLOCK: mode diversity too low: {modes}")
  sys.exit(1)
if len([x for x in polys if x]) < 2:
  print(f"BLOCK: policy_id diversity too low: {polys}")
  sys.exit(1)

print("OK")
PY

AI_GOLDEN_VECTORS_V2_DIVERSITY_OK=1
AI_GOLDEN_VECTORS_NO_RAW_OK=1
exit 0
