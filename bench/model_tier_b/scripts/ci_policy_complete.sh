#!/usr/bin/env bash
set -euo pipefail
umask 077

test -n "${BUTLER_BENCHMARK_POLICY_SHA256:-}" || { echo '{"status":"BLOCKED","fail_class":"POLICY_TRUST","detail_id":"POLICY_SHA_UNSET","exit_code":10}'; exit 10; }
test -n "${BUTLER_TRUST_POLICY_SHA256:-}" || { echo '{"status":"BLOCKED","fail_class":"POLICY_TRUST","detail_id":"TRUST_SHA_UNSET","exit_code":10}'; exit 10; }
python3 -m butler_bench.cli policy-check --policy policy/benchmark_policy.json --expected-sha256 "$BUTLER_BENCHMARK_POLICY_SHA256"
python3 -m butler_bench.cli trust-check --trust-policy policy/trust_policy.json --expected-sha256 "$BUTLER_TRUST_POLICY_SHA256"
