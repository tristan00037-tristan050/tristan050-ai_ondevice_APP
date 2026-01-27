#!/usr/bin/env bash
set -euo pipefail

CHART="webcore_appcore_starter_4_17/helm/onprem-gateway"

# secret.yaml에 if .Values.secrets.enabled 존재
rg -n "if .Values.secrets.enabled" "$CHART/templates/secret.yaml" -S >/dev/null 2>&1 || { echo "HELM_SECRETS_ENABLED_GUARD_OK=0"; exit 1; }

# deployment.yaml에 existingSecretName 존재
rg -n "existingSecretName" "$CHART/templates/deployment.yaml" -S >/dev/null 2>&1 || { echo "HELM_SECRETS_ENABLED_GUARD_OK=0"; exit 1; }

# deployment.yaml에 fail 가드 존재
rg -n "fail.*secrets.enabled" "$CHART/templates/deployment.yaml" -S >/dev/null 2>&1 || { echo "HELM_SECRETS_ENABLED_GUARD_OK=0"; exit 1; }

echo "HELM_SECRETS_ENABLED_GUARD_OK=1"

