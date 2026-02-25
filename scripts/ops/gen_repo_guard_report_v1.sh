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

# P6-P1-03B: preflight 먼저 실행하여 dist stamp = HEAD 보장 (DIST_FRESHNESS 통과 → energy 등 후속 가드 실행). fail-closed(|| true 없음).
bash tools/preflight_v1.sh >/dev/null 2>&1

# verify 실행 (stdout/stderr 모두 캡처). rc 반드시 수신, rc!=0이면 즉시 종료(쓰기/아카이브 없음). PR-P0-06 fail-closed.
RC=0
bash scripts/verify/verify_repo_contracts.sh >"$TMP_LOG" 2>&1 || RC=$?

if [ "$RC" -ne 0 ]; then
  echo "BLOCK: verify_repo_contracts failed (rc=$RC)"
  if ! grep -E "REPO_CONTRACTS_FAILED_GUARD=|REPO_GUARD_KEYS_ONLY_MODE_OK=" "$TMP_LOG" 2>/dev/null; then
    echo "REPO_CONTRACTS_FAILED_GUARD=(not in log)"
    echo "REPO_GUARD_KEYS_ONLY_MODE_OK=(not in log)"
  fi
  tail -n 200 "$TMP_LOG" || true
  exit "$RC"
fi

# rc==0일 때만 아래: KEY 추출 → json/md write → archive
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
# PR-P0-06: 이 블록은 rc==0일 때만 실행되므로, 성공 시 report.keys에 fail-closed 증명 키 추가.
kv["REPO_GUARD_REPORT_FAILCLOSED_OK"] = "1"

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

ARCHIVE_DIR="docs/ops/reports/archive"
mkdir -p "$ARCHIVE_DIR"

DAY_UTC="$(date -u +%Y-%m-%d)"

cp -f "docs/ops/reports/repo_contracts_latest.json" "$ARCHIVE_DIR/${DAY_UTC}_repo_contracts_latest.json"
cp -f "docs/ops/reports/repo_contracts_latest.md"   "$ARCHIVE_DIR/${DAY_UTC}_repo_contracts_latest.md"

echo "OK: archived $ARCHIVE_DIR/${DAY_UTC}_repo_contracts_latest.(json|md)"

