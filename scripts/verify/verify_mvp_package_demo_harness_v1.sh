#!/usr/bin/env bash
set -euo pipefail

DEMO_DOC_SEARCH_ALLOW_OK=0
DEMO_DOC_SEARCH_BLOCK_OK=0
DEMO_DOC_SEARCH_META_ONLY_OK=0
DEMO_DOC_SEARCH_REQUEST_ID_JOIN_OK=0

DEMO_WRITE_APPROVE_ALLOW_OK=0
DEMO_WRITE_APPROVE_BLOCK_OK=0
DEMO_WRITE_APPROVE_META_ONLY_OK=0
DEMO_WRITE_APPROVE_REQUEST_ID_JOIN_OK=0

DEMO_HELPDESK_ALLOW_OK=0
DEMO_HELPDESK_BLOCK_OK=0
DEMO_HELPDESK_META_ONLY_OK=0
DEMO_HELPDESK_REQUEST_ID_JOIN_OK=0

trap 'echo "DEMO_DOC_SEARCH_ALLOW_OK=${DEMO_DOC_SEARCH_ALLOW_OK}";
      echo "DEMO_DOC_SEARCH_BLOCK_OK=${DEMO_DOC_SEARCH_BLOCK_OK}";
      echo "DEMO_DOC_SEARCH_META_ONLY_OK=${DEMO_DOC_SEARCH_META_ONLY_OK}";
      echo "DEMO_DOC_SEARCH_REQUEST_ID_JOIN_OK=${DEMO_DOC_SEARCH_REQUEST_ID_JOIN_OK}";
      echo "DEMO_WRITE_APPROVE_ALLOW_OK=${DEMO_WRITE_APPROVE_ALLOW_OK}";
      echo "DEMO_WRITE_APPROVE_BLOCK_OK=${DEMO_WRITE_APPROVE_BLOCK_OK}";
      echo "DEMO_WRITE_APPROVE_META_ONLY_OK=${DEMO_WRITE_APPROVE_META_ONLY_OK}";
      echo "DEMO_WRITE_APPROVE_REQUEST_ID_JOIN_OK=${DEMO_WRITE_APPROVE_REQUEST_ID_JOIN_OK}";
      echo "DEMO_HELPDESK_ALLOW_OK=${DEMO_HELPDESK_ALLOW_OK}";
      echo "DEMO_HELPDESK_BLOCK_OK=${DEMO_HELPDESK_BLOCK_OK}";
      echo "DEMO_HELPDESK_META_ONLY_OK=${DEMO_HELPDESK_META_ONLY_OK}";
      echo "DEMO_HELPDESK_REQUEST_ID_JOIN_OK=${DEMO_HELPDESK_REQUEST_ID_JOIN_OK}"' EXIT

gen="scripts/demo/run_demo_harness_v1.sh"
test -x "$gen" || { echo "BLOCK: missing demo generator ($gen)"; exit 1; }

f1="docs/ops/reports/demo_doc_search_latest.json"
m1="docs/ops/reports/demo_doc_search_latest.md"
f2="docs/ops/reports/demo_write_approve_latest.json"
m2="docs/ops/reports/demo_write_approve_latest.md"
f3="docs/ops/reports/demo_helpdesk_ticket_latest.json"
m3="docs/ops/reports/demo_helpdesk_ticket_latest.md"

# P1: Generate artifacts if missing (keeps one-shot verify_repo_contracts working on clean checkout)
if [ ! -f "$f1" ] || [ ! -f "$f2" ] || [ ! -f "$f3" ] || [ ! -f "$m1" ] || [ ! -f "$m2" ] || [ ! -f "$m3" ]; then
  bash "$gen"
fi

test -f "$f1" || { echo "BLOCK: missing $f1"; exit 1; }
test -f "$m1" || { echo "BLOCK: missing $m1"; exit 1; }
test -f "$f2" || { echo "BLOCK: missing $f2"; exit 1; }
test -f "$m2" || { echo "BLOCK: missing $m2"; exit 1; }
test -f "$f3" || { echo "BLOCK: missing $f3"; exit 1; }
test -f "$m3" || { echo "BLOCK: missing $m3"; exit 1; }

# meta-only protections (long-line, banned key declarations)
banned="docs/ops/contracts/META_ONLY_BANNED_KEYS_V1.txt"
test -f "$banned" || { echo "BLOCK: missing banned keys SSOT ($banned)"; exit 1; }
keys_re="$(paste -sd'|' "$banned")"
[ -n "$keys_re" ] || { echo "BLOCK: empty banned keys SSOT"; exit 1; }

for f in "$f1" "$f2" "$f3" "$m1" "$m2" "$m3"; do
  if awk 'length($0) > 2000 { exit 10 }' "$f"; then :; else
    echo "BLOCK: long line detected in $f"; exit 1
  fi
done

if grep -EIn "\"(${keys_re})\"[[:space:]]*:" "$f1" "$f2" "$f3" >/dev/null 2>&1; then
  echo "BLOCK: banned key declaration detected in demo JSON outputs"
  exit 1
fi

# P2: Do NOT trust checks.* = 1 (self-attestation). Compute semantics here.
python3 - <<'PY'
import json, sys, re

pairs = [
  ("DOC_SEARCH", "docs/ops/reports/demo_doc_search_latest.json", "docs/ops/reports/demo_doc_search_latest.md"),
  ("WRITE_APPROVE", "docs/ops/reports/demo_write_approve_latest.json", "docs/ops/reports/demo_write_approve_latest.md"),
  ("HELPDESK", "docs/ops/reports/demo_helpdesk_ticket_latest.json", "docs/ops/reports/demo_helpdesk_ticket_latest.md"),
]

def block(msg):
  print("BLOCK:", msg)
  sys.exit(1)

for prefix, jpath, mpath in pairs:
  j = json.load(open(jpath,"r",encoding="utf-8"))
  md = open(mpath,"r",encoding="utf-8").read()

  # request_id join must be real: request_id in JSON must appear in MD
  rid = j.get("request_id")
  if not isinstance(rid,str) or len(rid) < 8:
    block(f"{prefix}: invalid request_id")
  if rid not in md:
    block(f"{prefix}: request_id not joinable between JSON and MD")

  # meta-only check: ensure no raw text fields in JSON (key-syntax)
  raw_keys = ["raw_text","rawText","raw_texts","rawTexts"]
  js_txt = open(jpath,"r",encoding="utf-8").read()
  for k in raw_keys:
    if re.search(r'"%s"\s*:' % re.escape(k), js_txt):
      block(f"{prefix}: raw key present: {k}")

  # allow/block semantics: require both allow_case and block_case objects exist
  allow_case = j.get("allow_case")
  block_case = j.get("block_case")
  if not isinstance(allow_case, dict):
    block(f"{prefix}: missing allow_case object")
  if not isinstance(block_case, dict):
    block(f"{prefix}: missing block_case object")

  # minimal evidence: decisions differ and have reason_code (code-only)
  if allow_case.get("decision") != "allow":
    block(f"{prefix}: allow_case.decision must be 'allow'")
  if block_case.get("decision") != "block":
    block(f"{prefix}: block_case.decision must be 'block'")
  if not isinstance(allow_case.get("reason_code"), str) or not allow_case["reason_code"]:
    block(f"{prefix}: allow_case.reason_code missing")
  if not isinstance(block_case.get("reason_code"), str) or not block_case["reason_code"]:
    block(f"{prefix}: block_case.reason_code missing")

print("OK")
PY

DEMO_DOC_SEARCH_ALLOW_OK=1
DEMO_DOC_SEARCH_BLOCK_OK=1
DEMO_DOC_SEARCH_META_ONLY_OK=1
DEMO_DOC_SEARCH_REQUEST_ID_JOIN_OK=1
DEMO_WRITE_APPROVE_ALLOW_OK=1
DEMO_WRITE_APPROVE_BLOCK_OK=1
DEMO_WRITE_APPROVE_META_ONLY_OK=1
DEMO_WRITE_APPROVE_REQUEST_ID_JOIN_OK=1
DEMO_HELPDESK_ALLOW_OK=1
DEMO_HELPDESK_BLOCK_OK=1
DEMO_HELPDESK_META_ONLY_OK=1
DEMO_HELPDESK_REQUEST_ID_JOIN_OK=1

exit 0
