#!/usr/bin/env bash
set -euo pipefail

ALGO_META_ONLY_FAILCLOSED_OK=0
ALGO_THREE_BLOCKS_NO_RAW_OK=0
ALGO_SIGNED_MANIFEST_VERIFY_OK=0
ALGO_P95_HOOK_OK=0

cleanup(){
  echo "ALGO_META_ONLY_FAILCLOSED_OK=${ALGO_META_ONLY_FAILCLOSED_OK}"
  echo "ALGO_THREE_BLOCKS_NO_RAW_OK=${ALGO_THREE_BLOCKS_NO_RAW_OK}"
  echo "ALGO_SIGNED_MANIFEST_VERIFY_OK=${ALGO_SIGNED_MANIFEST_VERIFY_OK}"
  echo "ALGO_P95_HOOK_OK=${ALGO_P95_HOOK_OK}"

  if [[ "${ALGO_META_ONLY_FAILCLOSED_OK}" == "1" ]] && \
     [[ "${ALGO_THREE_BLOCKS_NO_RAW_OK}" == "1" ]] && \
     [[ "${ALGO_SIGNED_MANIFEST_VERIFY_OK}" == "1" ]] && \
     [[ "${ALGO_P95_HOOK_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "BLOCK: python3 not found"; exit 1; }

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REQ="scripts/algo_core/sample_meta_request.json"
ALLOW="scripts/algo_core/meta_only_allowlist.json"
VALIDATOR="scripts/algo_core/validate_meta_only_request.mjs"
GEN="scripts/algo_core/generate_three_blocks.mjs"
SIGNER="scripts/algo_core/build_signed_manifest.mjs"
P95_SSOT="docs/ops/contracts/ALGO_CORE_P95_BUDGET_SSOT.json"

test -s "$REQ"
test -s "$ALLOW"
test -s "$VALIDATOR"
test -s "$GEN"
test -s "$SIGNER"
test -s "$P95_SSOT"

echo "== ALGO-CORE-01: meta-only fail-closed =="

# positive
node "$VALIDATOR" "$REQ" "$ALLOW" >/dev/null

# negative (forbidden key)
TMP_BAD="$(mktemp)"
cat >"$TMP_BAD" <<'JSON'
{
  "request_id":"bad",
  "intent":"X",
  "model_id":"Y",
  "prompt":"FORBIDDEN"
}
JSON

set +e
node "$VALIDATOR" "$TMP_BAD" "$ALLOW" >/dev/null 2>&1
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "BLOCK: validator did not fail on forbidden key"; exit 1; }

ALGO_META_ONLY_FAILCLOSED_OK=1

echo "== ALGO-CORE-02: three blocks, no raw =="

OUT_JSON="$(mktemp)"
node "$GEN" "$REQ" "$OUT_JSON" >/tmp/algo_core_latency.out

python3 - "$OUT_JSON" <<'PY'
import json, re, sys, pathlib
p = pathlib.Path(sys.argv[1])
o = json.loads(p.read_text("utf-8"))
if not isinstance(o, dict) or len(o.keys()) != 3:
  print("BLOCK: output must be object with exactly 3 top-level keys")
  sys.exit(1)
raw_pat = re.compile(r'"(prompt|raw|content|text|message|messages|input|context)"\s*:')
s = p.read_text("utf-8")
if raw_pat.search(s):
  print("BLOCK: forbidden key appeared in generated blocks")
  sys.exit(1)
PY

ALGO_THREE_BLOCKS_NO_RAW_OK=1

echo "== ALGO-CORE-03: signed manifest verify =="

node "$SIGNER" >/tmp/algo_core_sign.out
grep -q "^ALGO_SIGNED_MANIFEST_BUILT=1$" /tmp/algo_core_sign.out || { echo "BLOCK: missing ALGO_SIGNED_MANIFEST_BUILT=1"; exit 1; }

ALGO_SIGNED_MANIFEST_VERIFY_OK=1

echo "== ALGO-CORE-03: p95 hook gate =="

python3 - <<'PY'
import json, subprocess, tempfile, statistics, math, os, sys

ssot = json.load(open("docs/ops/contracts/ALGO_CORE_P95_BUDGET_SSOT.json", "r", encoding="utf-8"))
budget = int(ssot["p95_budget_ms"])
runs = int(ssot["sample_runs"])

def run_once():
  tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
  tf.close()
  try:
    out = subprocess.check_output(["node","scripts/algo_core/generate_three_blocks.mjs","scripts/algo_core/sample_meta_request.json", tf.name], text=True)
    # extract ALGO_LATENCY_MS
    for line in out.splitlines():
      if line.startswith("ALGO_LATENCY_MS="):
        return float(line.split("=",1)[1])
    raise RuntimeError("missing ALGO_LATENCY_MS")
  finally:
    try:
      os.unlink(tf.name)
    except:
      pass

vals = [run_once() for _ in range(runs)]
vals_sorted = sorted(vals)
k = math.ceil(0.95 * len(vals_sorted)) - 1
p95 = vals_sorted[max(0, min(k, len(vals_sorted)-1))]
print(f"P95_MS={p95:.3f} BUDGET_MS={budget}")
if p95 > budget:
  print("BLOCK: p95 too high")
  sys.exit(1)
PY

ALGO_P95_HOOK_OK=1
exit 0

