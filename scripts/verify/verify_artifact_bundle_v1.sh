#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_POLICY_V1_OK=0
ARTIFACT_BUNDLE_PRESENT_OK=0
ARTIFACT_BUNDLE_META_ONLY_OK=0

trap 'echo "ARTIFACT_BUNDLE_POLICY_V1_OK=$ARTIFACT_BUNDLE_POLICY_V1_OK";
      echo "ARTIFACT_BUNDLE_PRESENT_OK=$ARTIFACT_BUNDLE_PRESENT_OK";
      echo "ARTIFACT_BUNDLE_META_ONLY_OK=$ARTIFACT_BUNDLE_META_ONLY_OK"' EXIT

policy="docs/ops/contracts/ARTIFACT_BUNDLE_POLICY_V1.md"
gen="scripts/ops/gen_artifact_bundle_v1.sh"
out_json="docs/ops/reports/artifact_bundle_latest.json"
out_md="docs/ops/reports/artifact_bundle_latest.md"

test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "ARTIFACT_BUNDLE_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }
test -x "$gen" || { echo "BLOCK: missing or non-executable $gen"; exit 1; }

ARTIFACT_BUNDLE_POLICY_V1_OK=1

# 번들 파일이 없으면 1회 생성 (네트워크/설치 없음)
if [ ! -f "$out_json" ] || [ ! -f "$out_md" ]; then
  bash "$gen"
fi

test -f "$out_json" || { echo "BLOCK: missing $out_json"; exit 1; }
test -f "$out_md"   || { echo "BLOCK: missing $out_md"; exit 1; }
test -s "$out_json" || { echo "BLOCK: empty $out_json"; exit 1; }
test -s "$out_md"   || { echo "BLOCK: empty $out_md"; exit 1; }

ARTIFACT_BUNDLE_PRESENT_OK=1

# 긴 라인 차단(덤프 방지, EOF-safe)
while IFS= read -r line || [ -n "$line" ]; do
  if [ "${#line}" -ge 2000 ]; then
    echo "BLOCK: long line (>=2000 chars) in artifact bundle JSON"
    exit 1
  fi
done < "$out_json"

while IFS= read -r line || [ -n "$line" ]; do
  if [ "${#line}" -ge 2000 ]; then
    echo "BLOCK: long line (>=2000 chars) in artifact bundle MD"
    exit 1
  fi
done < "$out_md"

# 금지 키(원문 유입 경로) "키 선언" 차단 (가벼운 방어막)
# JSON 키 형태만 탐지:  "raw" : , "prompt":, "text":, "messages": 등
if grep -EIn '\"(raw|raw_text|rawText|prompt|text|messages|content|document_body)\"[[:space:]]*:' "$out_json" >/dev/null 2>&1; then
  echo "BLOCK: banned raw-like key declared in artifact bundle JSON"
  grep -EIn '\"(raw|raw_text|rawText|prompt|text|messages|content|document_body)\"[[:space:]]*:' "$out_json" | head -n 10
  exit 1
fi

ARTIFACT_BUNDLE_META_ONLY_OK=1
exit 0
