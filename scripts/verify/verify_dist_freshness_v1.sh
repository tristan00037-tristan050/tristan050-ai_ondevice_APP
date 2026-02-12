#!/usr/bin/env bash
set -euo pipefail

DIST_FRESHNESS_POLICY_V1_OK=0
DIST_BUILD_STAMP_PRESENT_OK=0
DIST_BUILD_STAMP_MATCH_HEAD_OK=0
trap '
echo "DIST_FRESHNESS_POLICY_V1_OK=$DIST_FRESHNESS_POLICY_V1_OK";
echo "DIST_BUILD_STAMP_PRESENT_OK=$DIST_BUILD_STAMP_PRESENT_OK";
echo "DIST_BUILD_STAMP_MATCH_HEAD_OK=$DIST_BUILD_STAMP_MATCH_HEAD_OK";
' EXIT

doc="docs/ops/contracts/DIST_FRESHNESS_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "DIST_FRESHNESS_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }
DIST_FRESHNESS_POLICY_V1_OK=1

# 대표 dist stamp 경로(실경로에 맞춤)
STAMP="webcore_appcore_starter_4_17/packages/bff-accounting/dist/.build_stamp.json"
[ -f "$STAMP" ] || { echo "BLOCK: missing stamp $STAMP"; exit 1; }
DIST_BUILD_STAMP_PRESENT_OK=1

command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

HEAD="$(git rev-parse HEAD)"

STAMP="$STAMP" HEAD="$HEAD" node - <<'NODE'
const fs = require("fs");
const p = process.env.STAMP;
const head = process.env.HEAD;
const j = JSON.parse(fs.readFileSync(p, "utf-8"));
if (!j || typeof j !== "object") { console.log("BLOCK: STAMP_INVALID"); process.exit(1); }
if (!j.git_sha || !j.built_at_utc || !j.workflow_name) { console.log("BLOCK: STAMP_FIELDS_MISSING"); process.exit(1); }
if (String(j.git_sha) !== String(head)) { console.log("BLOCK: STAMP_SHA_MISMATCH"); process.exit(1); }
process.exit(0);
NODE

DIST_BUILD_STAMP_MATCH_HEAD_OK=1
exit 0

