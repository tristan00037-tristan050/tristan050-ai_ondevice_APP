#!/usr/bin/env bash
set -euo pipefail

CHART="webcore_appcore_starter_4_17/helm/onprem-gateway"

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
run_n() { if have_rg; then rg -n "$1" "$2" -S >/dev/null 2>&1; else grep -nE "$1" "$2" >/dev/null 2>&1; fi; }

# secret.yaml에 if .Values.secrets.enabled 존재
run_n "if .Values.secrets.enabled" "$CHART/templates/secret.yaml" || { echo "ONPREM_HELM_SECRETS_GUARD_OK=0"; exit 1; }

# deployment.yaml에 existingSecretName 존재
run_n "existingSecretName" "$CHART/templates/deployment.yaml" || { echo "ONPREM_HELM_SECRETS_GUARD_OK=0"; exit 1; }

# deployment.yaml에 fail 가드 존재
run_n "fail.*secrets.enabled" "$CHART/templates/deployment.yaml" || { echo "ONPREM_HELM_SECRETS_GUARD_OK=0"; exit 1; }

echo "ONPREM_HELM_SECRETS_GUARD_OK=1"

