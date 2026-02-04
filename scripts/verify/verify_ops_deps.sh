#!/usr/bin/env bash
set -euo pipefail

OPS_DEPS_GIT_OK=0
OPS_DEPS_NODE_OK=0
OPS_DEPS_NPM_OK=0
OPS_DEPS_RG_OK=0
OPS_DEPS_JQ_OK=0
OPS_DEPS_PY_OK=0
OPS_DEPS_OK=0

cleanup(){
  echo "OPS_DEPS_GIT_OK=${OPS_DEPS_GIT_OK}"
  echo "OPS_DEPS_NODE_OK=${OPS_DEPS_NODE_OK}"
  echo "OPS_DEPS_NPM_OK=${OPS_DEPS_NPM_OK}"
  echo "OPS_DEPS_RG_OK=${OPS_DEPS_RG_OK}"
  echo "OPS_DEPS_JQ_OK=${OPS_DEPS_JQ_OK}"
  echo "OPS_DEPS_PY_OK=${OPS_DEPS_PY_OK}"
  echo "OPS_DEPS_OK=${OPS_DEPS_OK}"
}
trap cleanup EXIT

fail(){
  echo "FAIL: ops_deps_preflight ${1}"
  echo "HINT: install missing tools via workflow install steps."
  exit 1
}

need_cmd(){
  local cmd="$1" var="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    eval "$var=1"
  else
    fail "missing_cmd=${cmd}"
  fi
}

REQUIRE_NODE_NPM=0
REQUIRE_RG=0
REQUIRE_JQ=0
REQUIRE_PY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-node-npm) REQUIRE_NODE_NPM=1; shift ;;
    --require-rg) REQUIRE_RG=1; shift ;;
    --require-jq) REQUIRE_JQ=1; shift ;;
    --require-python) REQUIRE_PY=1; shift ;;
    *) fail "unknown_arg=$1" ;;
  esac
done

need_cmd git OPS_DEPS_GIT_OK

if [[ "$REQUIRE_NODE_NPM" -eq 1 ]]; then
  need_cmd node OPS_DEPS_NODE_OK
  need_cmd npm  OPS_DEPS_NPM_OK
fi

if [[ "$REQUIRE_RG" -eq 1 ]]; then
  need_cmd rg OPS_DEPS_RG_OK
else
  if command -v rg >/dev/null 2>&1; then OPS_DEPS_RG_OK=1; fi
fi

if [[ "$REQUIRE_JQ" -eq 1 ]]; then
  need_cmd jq OPS_DEPS_JQ_OK
else
  if command -v jq >/dev/null 2>&1; then OPS_DEPS_JQ_OK=1; fi
fi

if [[ "$REQUIRE_PY" -eq 1 ]]; then
  need_cmd python3 OPS_DEPS_PY_OK
else
  if command -v python3 >/dev/null 2>&1; then OPS_DEPS_PY_OK=1; fi
fi

OPS_DEPS_OK=1
exit 0

