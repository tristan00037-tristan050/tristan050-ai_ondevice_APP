#!/usr/bin/env bash
set -euo pipefail

# AI 미니 실행모드 (meta-only)
# - golden vectors v2
# - variance/outlier guard
# - energy proxy stability guard
#
# 출력:
# - docs/ops/reports/ai_smoke_latest.md
# - docs/ops/reports/ai_smoke_latest.json

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUTDIR="docs/ops/reports"
mkdir -p "$OUTDIR"

TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run_step() {
  local name="$1"
  shift
  local log="$TMP/${name}.log"
  set +e
  "$@" >"$log" 2>&1
  local rc=$?
  set -e
  echo "$rc" >"$TMP/${name}.rc"
}

# 1) golden vectors v2
run_step "golden_vectors_v2" bash scripts/verify/verify_ai_golden_vectors_v2.sh

# 2) variance/outlier
run_step "variance_outlier_v1" bash scripts/verify/verify_ai_variance_outlier_v1.sh

# 3) energy proxy
run_step "energy_proxy_v1" bash scripts/verify/verify_ai_energy_proxy_v1.sh

python - <<'PY' "$OUTDIR" "$TS_UTC" "$GIT_SHA" "$BRANCH" "$TMP"
import json, os, re, sys

outdir, ts_utc, git_sha, branch, tmpdir = sys.argv[1:]

key_re = re.compile(r'^([A-Z0-9_]+)=([0-9]+|true|false|[A-Za-z0-9_.:-]+)$')

def parse_keys(log_path):
    kv = {}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = key_re.match(line)
            if m:
                kv[m.group(1)] = m.group(2)
    return kv

def load_rc(name):
    with open(os.path.join(tmpdir, f"{name}.rc"), "r", encoding="utf-8") as f:
        return int(f.read().strip() or "1")

steps = [
    ("golden_vectors_v2", "scripts/verify/verify_ai_golden_vectors_v2.sh"),
    ("variance_outlier_v1", "scripts/verify/verify_ai_variance_outlier_v1.sh"),
    ("energy_proxy_v1", "scripts/verify/verify_ai_energy_proxy_v1.sh"),
]

results = []
for name, cmd in steps:
    log_path = os.path.join(tmpdir, f"{name}.log")
    rc = load_rc(name)
    kv = parse_keys(log_path)
    results.append({
        "name": name,
        "cmd": cmd,
        "exit_code": rc,
        "keys": kv,
    })

report = {
    "schema": "ai_smoke_report_v1",
    "ts_utc": ts_utc,
    "git_sha": git_sha,
    "branch": branch,
    "results": results,
}

json_path = os.path.join(outdir, "ai_smoke_latest.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

md = []
md.append("# AI Smoke Report (latest)")
md.append("")
md.append(f"- ts_utc: {ts_utc}")
md.append(f"- git_sha: {git_sha}")
md.append(f"- branch: {branch}")
md.append("")
for r in results:
    md.append(f"## {r['name']}")
    md.append(f"- exit_code: {r['exit_code']}")
    md.append("")
    md.append("| key | value |")
    md.append("|---|---|")
    for k in sorted(r["keys"].keys()):
        md.append(f"| {k} | {r['keys'][k]} |")
    md.append("")

md_path = os.path.join(outdir, "ai_smoke_latest.md")
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")

print(f"OK: wrote {json_path}")
print(f"OK: wrote {md_path}")
PY

