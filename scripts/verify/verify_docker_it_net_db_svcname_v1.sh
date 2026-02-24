#!/usr/bin/env bash
# PR-P0-DEPLOY-03: Verify docker it-net + postgres16 service name (no host.docker.internal).
# Scope: .github/workflows, scripts/ops, scripts/verify. Output: key=value only (meta-only).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
host_docker_internal_used=0
DOCKER_IT_NET_DB_SVCNAME_V1_OK=0
HOST_DOCKER_INTERNAL_FORBIDDEN_OK=0

# Scan for host.docker.internal *usage* (BLOCK): connection URL, add-host, etc. Ignore comments and hint text.
check_usage() {
  local line="$1"
  local rest="${line#*:}"
  local content="${rest#*:}"
  content="${content#"${content%%[![:space:]]*}"}"
  [[ "$content" =~ ^[[:space:]]*# ]] && return 1
  # Actual usage: @host.docker.internal, :host.docker.internal, add-host.*host.docker.internal
  [[ "$content" =~ @host\.docker\.internal ]] && return 0
  [[ "$content" =~ host\.docker\.internal:[0-9]+ ]] && return 0
  [[ "$content" =~ add-host.*host\.docker\.internal ]] && return 0
  [[ "$content" =~ host\.docker\.internal.*host-gateway ]] && return 0
  return 1
}
if command -v rg >/dev/null 2>&1; then
  while IFS= read -r hit; do
    [[ -z "$hit" ]] && continue
    check_usage "$hit" && { host_docker_internal_used=1; break; }
  done < <(rg -n --no-ignore "host\.docker\.internal" \
    "$REPO_ROOT/.github/workflows" \
    "$REPO_ROOT/scripts/ops" \
    "$REPO_ROOT/scripts/verify" \
    2>/dev/null || true)
else
  while IFS= read -r hit; do
    [[ -z "$hit" ]] && continue
    check_usage "$hit" && { host_docker_internal_used=1; break; }
  done < <(grep -R --include="*.yml" --include="*.yaml" --include="*.sh" -n "host\.docker\.internal" \
    "$REPO_ROOT/.github/workflows" \
    "$REPO_ROOT/scripts/ops" \
    "$REPO_ROOT/scripts/verify" \
    2>/dev/null || true)
fi

if [[ "$host_docker_internal_used" = "1" ]]; then
  HOST_DOCKER_INTERNAL_FORBIDDEN_OK=0
  echo "docker_it_net_exit_code=1"
  echo "docker_it_net_fail_class=unknown"
  echo "docker_it_net_fail_hint=host.docker.internal forbidden (BLOCK)"
  echo "docker_it_net_name=it-net-v1"
  echo "docker_db_container_name=postgres16"
  echo "docker_bff_container_name=bff"
  echo "docker_db_port=5432"
  echo "docker_db_host=postgres16"
  echo "docker_database_url_scheme=postgres"
  echo "host_docker_internal_used=1"
  echo "DOCKER_IT_NET_DB_SVCNAME_V1_OK=0"
  echo "HOST_DOCKER_INTERNAL_FORBIDDEN_OK=0"
  exit 1
fi

HOST_DOCKER_INTERNAL_FORBIDDEN_OK=1

# Run SSOT script (with BFF_IMAGE if set for full verify)
set +e
out=$(cd "$REPO_ROOT" && bash scripts/ops/docker_it_net_db_svcname_v1.sh 2>&1)
rc=$?
set -e

# Emit keys from script output (no connection strings / secrets)
while IFS= read -r line; do
  case "$line" in
    docker_it_net_*|docker_db_*|docker_bff_*|docker_database_*)
      echo "$line"
      ;;
    *) ;;
  esac
done <<< "$out"

echo "host_docker_internal_used=0"

if [[ "$rc" -eq 0 ]]; then
  echo "DOCKER_IT_NET_DB_SVCNAME_V1_OK=1"
  echo "HOST_DOCKER_INTERNAL_FORBIDDEN_OK=1"
  exit 0
fi

echo "DOCKER_IT_NET_DB_SVCNAME_V1_OK=0"
echo "HOST_DOCKER_INTERNAL_FORBIDDEN_OK=1"
exit 1
