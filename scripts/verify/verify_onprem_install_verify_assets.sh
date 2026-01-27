#!/usr/bin/env bash
set -euo pipefail

ONPREM_INSTALL_VERIFY_OK=0
cleanup(){ echo "ONPREM_INSTALL_VERIFY_OK=${ONPREM_INSTALL_VERIFY_OK}"; }
trap cleanup EXIT

test -s webcore_appcore_starter_4_17/docs/ONPREM_INSTALL_VERIFY.md
test -x webcore_appcore_starter_4_17/scripts/ops/verify_onprem_install.sh

ONPREM_INSTALL_VERIFY_OK=1
exit 0
