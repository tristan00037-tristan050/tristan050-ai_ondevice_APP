#!/usr/bin/env bash
set -euo pipefail

ONPREM_INSTALL_VERIFY_OK=0
cleanup(){ echo "ONPREM_INSTALL_VERIFY_OK=${ONPREM_INSTALL_VERIFY_OK}"; }
trap cleanup EXIT

test -s webcore_appcore_starter_4_17/docs/ONPREM_INSTALL_VERIFY.md
test -d webcore_appcore_starter_4_17/helm/onprem-gateway

bash scripts/verify/verify_repo_contracts.sh >/tmp/onprem_repo_guards.log
grep -q "ONPREM_HELM_SECRETS_GUARD_OK=1" /tmp/onprem_repo_guards.log

ONPREM_INSTALL_VERIFY_OK=1
exit 0
