#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ $# -eq 7 ]] || { echo '{"status":"BLOCKED","fail_class":"PREFLIGHT","detail_id":"USAGE","exit_code":10}'; exit 10; }
python3 -m butler_bench.cli policy-check --policy "$1" --expected-sha256 "$2"
python3 -m butler_bench.cli trust-check --trust-policy "$3" --expected-sha256 "$4"
python3 -m butler_bench.cli m3-gate-check --receipts-dir "$5" --expected-subjects "$6" --expected-subjects-sha256 "$7"
