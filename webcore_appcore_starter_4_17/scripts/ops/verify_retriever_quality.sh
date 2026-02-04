#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh

GSET="${GSET:-docs/ops/r10-s7-retriever-goldenset.jsonl}"
SCHEMA="${SCHEMA:-docs/ops/r10-s7-retriever-goldenset.schema.json}"
OUT_DIR="${OUT_DIR:-docs/ops}"
REPORT="${REPORT:-$OUT_DIR/r10-s7-retriever-quality-phase0-report.json}"

fail() { echo "FAIL: $*" >&2; exit 1; }

test -f "$GSET" || fail "goldenset not found: $GSET"
test -f "$SCHEMA" || fail "schema not found: $SCHEMA"

python3 - <<'PY' "$SCHEMA"
import json, sys
p = sys.argv[1]
try:
    json.load(open(p, "r", encoding="utf-8"))
except Exception as e:
    raise SystemExit(f"FAIL: invalid schema json: {e}")
print("OK: schema json parseable")
PY

python3 - <<'PY' "$GSET"
import json, sys, re
p = sys.argv[1]
req = {"schema_version","id","locale","query","expected"}
id_re = re.compile(r"^[a-z0-9][a-z0-9\\-]{3,64}$")
sv = "r10-s7-retriever-goldenset/v1"
ok_lines = 0
with open(p,"r",encoding="utf-8") as f:
    for i,line in enumerate(f,1):
        line=line.strip()
        if not line:
            continue
        ok_lines += 1
        try:
            j=json.loads(line)
        except Exception as e:
            raise SystemExit(f"FAIL: invalid JSON at line {i}: {e}")
        miss = req - set(j.keys())
        if miss:
            raise SystemExit(f"FAIL: missing keys at line {i}: {sorted(miss)}")
        if j["schema_version"] != sv:
            raise SystemExit(f"FAIL: schema_version mismatch at line {i}")
        if not id_re.match(str(j["id"])):
            raise SystemExit(f"FAIL: invalid id format at line {i}")
        exp=j.get("expected") or {}
        if "must_have_any" not in exp or "must_not_have_any" not in exp:
            raise SystemExit(f"FAIL: expected.* missing at line {i}")
if ok_lines < 20:
    raise SystemExit(f"FAIL: goldenset must have >=20 lines (got {ok_lines})")
print(f"OK: goldenset jsonl basic validity (lines={ok_lines})")
PY

mkdir -p "$OUT_DIR"
python3 - <<'PY' "$GSET" "$SCHEMA" "$REPORT"
import hashlib, json, sys, time
gset, schema, out = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(gset,"rb").read()
sha_g = hashlib.sha256(raw).hexdigest()
sha_s = hashlib.sha256(open(schema,"rb").read()).hexdigest()
lines = [ln for ln in open(gset,"r",encoding="utf-8").read().splitlines() if ln.strip()]
report = {
  "ok": True,
  "phase": "S7/Phase0",
  "meta_only": True,
  "goldenset": {"path": gset, "lines": len(lines), "sha256": sha_g},
  "schema": {"path": schema, "sha256": sha_s},
  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}
open(out,"w",encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
# meta-only guard (no query/raw text keys)
s = json.dumps(report, ensure_ascii=False)
for bad in ["query", "content", "text", "payload"]:
    if f'"{bad}"' in s:
        raise SystemExit(f"FAIL: report contains forbidden key: {bad}")
print(f"OK: meta-only report written: {out}")
PY

echo "OK: verify_retriever_quality (Phase0 meta-only) exit 0"

