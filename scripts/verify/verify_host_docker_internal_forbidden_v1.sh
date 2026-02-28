#!/usr/bin/env bash
# PR-P0-DEPLOY-03: Static scan only — no Docker required. Forbid host.docker.internal usage.
# Scope: .github/workflows, scripts/ops, scripts/verify. Used by verify_repo_contracts.sh (always).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
host_docker_internal_used=0

# Scan for host.docker.internal *usage* (BLOCK): connection URL, add-host, etc. Ignore comments and hint text.
check_usage() {
  local line="$1"
  local rest="${line#*:}"
  local content="${rest#*:}"
  content="${content#"${content%%[![:space:]]*}"}"
  [[ "$content" =~ ^[[:space:]]*# ]] && return 1
  [[ "$content" =~ @host\.docker\.internal ]] && return 0
  [[ "$content" =~ host\.docker\.internal:[0-9]+ ]] && return 0
  [[ "$content" =~ add-host.*host\.docker\.internal ]] && return 0
  [[ "$content" =~ host\.docker\.internal.*host-gateway ]] && return 0
  return 1
}

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
if have_rg; then
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
  echo "HOST_DOCKER_INTERNAL_FORBIDDEN_OK=0"
  exit 1
fi

echo "HOST_DOCKER_INTERNAL_FORBIDDEN_OK=1"
exit 0
