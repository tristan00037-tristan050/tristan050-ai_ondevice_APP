#!/usr/bin/env bash
set -euo pipefail

# decision-only generator (no DoD keys, no secrets, no network)
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

policy="docs/ops/contracts/ARTIFACT_BUNDLE_POLICY_V1.md"
test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "ARTIFACT_BUNDLE_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

out_json="docs/ops/reports/artifact_bundle_latest.json"
out_md="docs/ops/reports/artifact_bundle_latest.md"
mkdir -p docs/ops/reports

rc_json="docs/ops/reports/repo_contracts_latest.json"
rc_md="docs/ops/reports/repo_contracts_latest.md"
ai_json="docs/ops/reports/ai_smoke_latest.json"
ai_md="docs/ops/reports/ai_smoke_latest.md"

# 입력 리포트가 없으면 생성 (CI clean checkout 대비)
if [ ! -f "$rc_json" ] || [ ! -f "$rc_md" ]; then
  ARTIFACT_BUNDLE_GEN_IN_PROGRESS=1 bash scripts/ops/gen_repo_guard_report_v1.sh
fi

if [ ! -f "$ai_json" ] || [ ! -f "$ai_md" ]; then
  ARTIFACT_BUNDLE_GEN_IN_PROGRESS=1 bash scripts/ops/run_ai_smoke_v1.sh
fi

# 입력 리포트가 없으면 fail-closed
test -f "$rc_json" || { echo "BLOCK: missing $rc_json"; exit 1; }
test -f "$rc_md"   || { echo "BLOCK: missing $rc_md"; exit 1; }
test -f "$ai_json" || { echo "BLOCK: missing $ai_json"; exit 1; }
test -f "$ai_md"   || { echo "BLOCK: missing $ai_md"; exit 1; }

git_sha="$(git rev-parse HEAD)"
ts_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# 번들은 "포인터 + 최소 메타"만 기록 (원문/리포트 본문을 복사하지 않음)
cat > "$out_json" <<EOF
{
  "schema": "artifact_bundle_v1",
  "ts_utc": "${ts_utc}",
  "git_sha": "${git_sha}",
  "inputs": {
    "repo_contracts_latest_json": "${rc_json}",
    "repo_contracts_latest_md": "${rc_md}",
    "ai_smoke_latest_json": "${ai_json}",
    "ai_smoke_latest_md": "${ai_md}"
  }
}
EOF

cat > "$out_md" <<EOF
# Artifact Bundle (latest)

- ts_utc: ${ts_utc}
- git_sha: ${git_sha}

## Inputs
- repo_contracts_latest: ${rc_json}, ${rc_md}
- ai_smoke_latest: ${ai_json}, ${ai_md}
EOF

test -s "$out_json"
test -s "$out_md"
exit 0
