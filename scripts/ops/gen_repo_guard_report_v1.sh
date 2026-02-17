#!/usr/bin/env bash
set -euo pipefail

# repo-wide verify 결과를 meta-only 리포트로 저장한다.
# 출력:
# - docs/ops/reports/repo_contracts_latest.json
# - docs/ops/reports/repo_contracts_latest.md
#
# 원문/로그 전문을 저장하지 않고, KEY=VALUE만 추출하여 저장한다.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUTDIR="docs/ops/reports"
mkdir -p "$OUTDIR"

TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

TMP_LOG="$(mktemp)"
trap 'rm -f "$TMP_LOG"' EXIT

# verify 실행 (stdout/stderr 모두 캡처)
bash scripts/verify/verify_repo_contracts.sh >"$TMP_LOG" 2>&1 || true

# KEY=VALUE 라인만 추출(중복 키는 마지막 값을 채택)
PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "BLOCK: python3/python not found"; exit 1; }

"$PYTHON_BIN" - <<'PY' "$TMP_LOG" "$OUTDIR" "$TS_UTC" "$GIT_SHA" "$BRANCH"
import json, re, sys, os, datetime

log_path, outdir, ts_utc, git_sha, branch = sys.argv[1:]
kv = {}
key_re = re.compile(r'^([A-Z0-9_]+)=([0-9]+|true|false|[A-Za-z0-9_.:-]+)$')

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        m = key_re.match(line)
        if m:
            kv[m.group(1)] = m.group(2)

# overall status (meta-only)
exit_code = 0 if kv.get("REPO_CONTRACTS_HYGIENE_OK") == "1" else 1
# 실제 EXIT=0을 엄밀히 기록하려면 verify 종료코드를 받아야 하나,
# 이 스크립트는 '키 기반 상태'만 저장한다(원문/로그 전문 0).
# repo guards 최종 상태는 caller가 EXIT를 확인하면 된다.

report = {
    "schema": "repo_contracts_report_v1",
    "ts_utc": ts_utc,
    "git_sha": git_sha,
    "branch": branch,
    "keys": kv,
}

json_path = os.path.join(outdir, "repo_contracts_latest.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# md 요약(상위 키만 표로)
md_path = os.path.join(outdir, "repo_contracts_latest.md")
lines = []
lines.append(f"# Repo Contracts Report (latest)")
lines.append("")
lines.append(f"- ts_utc: {ts_utc}")
lines.append(f"- git_sha: {git_sha}")
lines.append(f"- branch: {branch}")
lines.append("")
lines.append("| key | value |")
lines.append("|---|---|")
for k in sorted(kv.keys()):
    lines.append(f"| {k} | {kv[k]} |")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"OK: wrote {json_path}")
print(f"OK: wrote {md_path}")
PY

