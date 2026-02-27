#!/usr/bin/env bash
set -euo pipefail

OUTDIR=""
P95_MAX_MS=""

usage() {
  echo "Usage: $0 --outdir <dir> --p95-max-ms <int>"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir) OUTDIR="${2:-}"; shift 2;;
    --p95-max-ms) P95_MAX_MS="${2:-}"; shift 2;;
    *) usage;;
  esac
done

[[ -n "$OUTDIR" && -n "$P95_MAX_MS" ]] || usage
[[ -f "$OUTDIR/result.jsonl" ]] || { echo "BLOCK: missing $OUTDIR/result.jsonl" >&2; exit 1; }

python3 - "$OUTDIR/result.jsonl" "$P95_MAX_MS" <<'PY'
import json,sys
p=sys.argv[1]
p95_max=int(sys.argv[2])

lat=[]
with open(p,'r',encoding='utf-8') as f:
  for line in f:
    line=line.strip()
    if not line: continue
    o=json.loads(line)
    v=o.get("latency_ms", None)
    if v is None:
      raise SystemExit("BLOCK: missing latency_ms in result.jsonl")
    lat.append(int(v))

lat.sort()
n=len(lat)
if n==0:
  raise SystemExit("BLOCK: no latency samples")

# p95 index using (n-1) scaling
idx=int((n-1)*95/100)
idx=max(0, min(idx, n-1))
p95=lat[idx]

print(f"EXEC_MODE_LATENCY_P95_MS={p95}")
if p95 > p95_max:
  raise SystemExit(f"BLOCK: latency_p95_ms {p95} > p95_max_ms {p95_max}")

print("EXEC_MODE_LATENCY_GATE_V1_OK=1")
PY
