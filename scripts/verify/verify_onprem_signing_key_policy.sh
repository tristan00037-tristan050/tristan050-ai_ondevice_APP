#!/usr/bin/env bash
set -euo pipefail

ONPREM_SIGNING_KEY_REQUIRED_OK=0
ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=0
ONPREM_KEY_ID_ALLOWLIST_OK=0

cleanup(){
  echo "ONPREM_SIGNING_KEY_REQUIRED_OK=${ONPREM_SIGNING_KEY_REQUIRED_OK}"
  echo "ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=${ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK}"
  echo "ONPREM_KEY_ID_ALLOWLIST_OK=${ONPREM_KEY_ID_ALLOWLIST_OK}"
}
trap cleanup EXIT

# 1) prod mode without keys must FAIL (required keys enforced; ephemeral forbidden)
set +e
ONPREM_MODE=prod node webcore_appcore_starter_4_17/scripts/ops/build_onprem_signed_bundle.mjs >/tmp/onprem06_prod_missing_keys.log 2>&1
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  echo "BLOCK: prod mode unexpectedly succeeded without keys"
  exit 1
fi
grep -q "requires ONPREM_BUNDLE_SIGN_PUBLIC_KEY_B64" /tmp/onprem06_prod_missing_keys.log
ONPREM_SIGNING_KEY_REQUIRED_OK=1
ONPREM_EPHEMERAL_KEY_FORBIDDEN_OK=1

# 2) prod mode with keys but key_id not in allowlist must FAIL BEFORE signing
#    (keys can be dummy non-empty strings; policy check happens first)
set +e
ONPREM_MODE=prod \
ONPREM_BUNDLE_SIGN_PUBLIC_KEY_B64="x" \
ONPREM_BUNDLE_SIGN_PRIVATE_KEY_B64="y" \
ONPREM_SIGNING_KEY_ID="bad" \
ONPREM_ALLOWED_SIGNING_KEY_IDS="good1,good2" \
node webcore_appcore_starter_4_17/scripts/ops/build_onprem_signed_bundle.mjs >/tmp/onprem06_prod_bad_keyid.log 2>&1
RC2=$?
set -e
if [[ $RC2 -eq 0 ]]; then
  echo "BLOCK: prod mode unexpectedly succeeded with key_id outside allowlist"
  exit 1
fi
grep -q "not in allowlist" /tmp/onprem06_prod_bad_keyid.log
ONPREM_KEY_ID_ALLOWLIST_OK=1

exit 0
