#!/usr/bin/env bash
set -euo pipefail

EXEC_MODE_LATENCY_MEASURE_PRESENT_OK=0
EXEC_MODE_LATENCY_MISSING_BLOCK_OK=0

finish() {
  echo "EXEC_MODE_LATENCY_MEASURE_PRESENT_OK=${EXEC_MODE_LATENCY_MEASURE_PRESENT_OK}"
  echo "EXEC_MODE_LATENCY_MISSING_BLOCK_OK=${EXEC_MODE_LATENCY_MISSING_BLOCK_OK}"
}
trap finish EXIT

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT_ROOT="${OUT_ROOT:-out}"

# result.jsonl이 없으면 SKIP(일반 repo-wide verify false-fail 방지)
files="${FILES:-$(find "$OUT_ROOT" -type f -name "result.jsonl" 2>/dev/null | sort || true)}"
if [ -z "${files}" ]; then
  exit 0
fi

export FILES="$files"
node - <<'NODE'
const fs = require("fs");
const path = require("path");

const raw = (process.env.FILES || "").trim();
const files = raw ? raw.split(/\r?\n/).filter(Boolean) : [];
let ok = true;

for (const f of files) {
  const abspath = path.isAbsolute(f) ? f : path.join(process.cwd(), f);
  let content;
  try {
    content = fs.readFileSync(abspath, "utf8");
  } catch {
    ok = false;
    continue;
  }
  const lines = content.split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      ok = false;
      continue;
    }
    const v = obj.latency_us;
    if (typeof v !== "number" || !Number.isInteger(v) || v <= 0) {
      ok = false;
    }
  }
}

process.exit(ok ? 0 : 1);
NODE

EXEC_MODE_LATENCY_MEASURE_PRESENT_OK=1
EXEC_MODE_LATENCY_MISSING_BLOCK_OK=1
exit 0
