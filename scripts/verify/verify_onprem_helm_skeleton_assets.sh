#!/usr/bin/env bash
set -euo pipefail

CHART="webcore_appcore_starter_4_17/helm/onprem-gateway"

test -f "$CHART/Chart.yaml" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }
test -f "$CHART/values.yaml" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }
test -f "$CHART/values.schema.json" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }

test -f "$CHART/templates/deployment.yaml" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }
test -f "$CHART/templates/service.yaml" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }
test -f "$CHART/templates/secret.yaml" || { echo "ONPREM_HELM_SKELETON_OK=0"; exit 1; }

echo "ONPREM_HELM_SKELETON_OK=1"

