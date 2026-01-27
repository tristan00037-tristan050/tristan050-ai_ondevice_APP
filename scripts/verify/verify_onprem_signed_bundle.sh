#!/usr/bin/env bash
set -euo pipefail

ONPREM_SIGNED_BUNDLE_OK=0
cleanup(){ echo "ONPREM_SIGNED_BUNDLE_OK=${ONPREM_SIGNED_BUNDLE_OK}"; }
trap cleanup EXIT

node webcore_appcore_starter_4_17/scripts/ops/build_onprem_signed_bundle.mjs >/tmp/onprem_bundle_build.log

grep -q "ONPREM_SIGNED_BUNDLE_OK=1" /tmp/onprem_bundle_build.log

test -s dist/onprem_bundle_manifest.json
test -s dist/onprem_bundle_manifest.sig.b64

ONPREM_SIGNED_BUNDLE_OK=1
exit 0
