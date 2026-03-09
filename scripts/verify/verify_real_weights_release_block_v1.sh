#!/usr/bin/env bash
set -euo pipefail

# P23-P0A-03: REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE
# ENFORCE=0 by default (packs are in pending state)
REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_OK=0
trap 'echo "REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_OK=${REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_OK}"' EXIT

ENFORCE="${REAL_WEIGHTS_RELEASE_BLOCK_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_SKIPPED=1"
  REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_OK=0
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python3 <<'PY'
import glob, json, sys

targets = (
    glob.glob("packs/*/manifest.json")
    + glob.glob("packs/*/provenance.json")
    + glob.glob("packs/*/sbom.json")
    + glob.glob("packs/*/eval_fingerprint.json")
)

PLACEHOLDER_VALUES = {
    "pending_real_weights",
    "pending_ai09",
    "REQUIRED",
    "COMPUTED_AT_EVAL_TIME",
    "COMPUTED_AT_PACK_BUILD_TIME",
}

bad = 0
for path in targets:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    status = obj.get("status")
    if status not in (None, "verified"):
        if status in PLACEHOLDER_VALUES or status.startswith("pending"):
            print("ERROR_CODE=ARTIFACT_STATUS_PENDING")
            print(f"HIT_PATH={path}")
            print(f"STATUS={status}")
            bad = 1
            continue

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
        else:
            yield x

    for v in walk(obj):
        if isinstance(v, str) and v in PLACEHOLDER_VALUES:
            print("ERROR_CODE=PLACEHOLDER_VALUE_DETECTED")
            print(f"HIT_PATH={path}")
            print(f"HIT_VALUE={v}")
            bad = 1
            break

if bad:
    sys.exit(1)
PY

REAL_WEIGHTS_PRESENT_REQUIRED_FOR_RELEASE_OK=1
exit 0
