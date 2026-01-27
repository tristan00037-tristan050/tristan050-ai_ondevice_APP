#!/usr/bin/env bash
set -euo pipefail

ONPREM_HELM_TEMPLATE_SMOKE_OK=0
ONPREM_HELM_TEMPLATE_SECRET_REF_OK=0
cleanup(){
  echo "ONPREM_HELM_TEMPLATE_SMOKE_OK=${ONPREM_HELM_TEMPLATE_SMOKE_OK}";
  echo "ONPREM_HELM_TEMPLATE_SECRET_REF_OK=${ONPREM_HELM_TEMPLATE_SECRET_REF_OK}";
}
trap cleanup EXIT

CHART="webcore_appcore_starter_4_17/helm/onprem-gateway"

# Helm command resolver: prefer local helm; fallback to dockerized helm
helm_cmd() {
  if command -v helm >/dev/null 2>&1; then
    helm "$@"
  else
    # docker fallback (no install)
    docker run --rm -i \
      -v "$(pwd)":/work -w /work \
      alpine/helm:3.14.4 "$@"
  fi
}

# 케이스 A: enabled=true면 Secret이 렌더 결과에 있어야 함
helm_cmd template t "$CHART" \
  --set secrets.enabled=true \
  --set secrets.DATABASE_URL="postgres://example" \
  --set secrets.EXPORT_SIGN_SECRET="x" \
| grep -q "kind: Secret"

# 케이스 B: enabled=false + existingSecretName 비어 있으면 반드시 fail-closed 문구가 나와야 함
set +e
OUT="$(helm_cmd template t "$CHART" --set secrets.enabled=false 2>&1)"
RC=$?
set -e

# helm template 자체가 성공하면(=fail-closed가 안 걸리면) BLOCK
if [[ $RC -eq 0 ]]; then
  echo "BLOCK: expected helm template to fail when secrets.enabled=false and existingSecretName is empty"
  echo "$OUT"
  exit 1
fi

echo "$OUT" | grep -q "secrets.enabled=false requires secrets.existingSecretName"

# 케이스 C: enabled=false + existingSecretName=abc => Deployment가 abc를 참조해야 함
OUTC="$(helm_cmd template t "$CHART" --set secrets.enabled=false --set secrets.existingSecretName=abc 2>&1)"
# EXPORT_SIGN_SECRET env 블록의 secretKeyRef.name만 정확히 검사 (false positive 방지)
EXPORT_REF_NAME="$(
  echo "$OUTC" | awk '
    $0 ~ /- name: EXPORT_SIGN_SECRET/ {in_env=1; next}
    in_env && $0 ~ /secretKeyRef:/ {in_ref=1; next}
    in_env && in_ref && $0 ~ /^[[:space:]]*name:/ {
      sub(/^[[:space:]]*name:[[:space:]]*/, "", $0);
      print $0;
      exit
    }
  '
)"
if [[ -z "${EXPORT_REF_NAME:-}" ]]; then
  echo "BLOCK: could not find secretKeyRef.name for EXPORT_SIGN_SECRET"
  exit 1
fi
echo "${EXPORT_REF_NAME}" | grep -qx "abc"

ONPREM_HELM_TEMPLATE_SECRET_REF_OK=1
ONPREM_HELM_TEMPLATE_SMOKE_OK=1
exit 0
