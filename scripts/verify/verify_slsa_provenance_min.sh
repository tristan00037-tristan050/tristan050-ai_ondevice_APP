#!/usr/bin/env bash
set -euo pipefail

SLSA_PROVENANCE_PRESENT_OK=0
SLSA_PROVENANCE_FORMAT_OK=0
SLSA_PROVENANCE_LINK_OK=0

cleanup(){
  echo "SLSA_PROVENANCE_PRESENT_OK=${SLSA_PROVENANCE_PRESENT_OK}"
  echo "SLSA_PROVENANCE_FORMAT_OK=${SLSA_PROVENANCE_FORMAT_OK}"
  echo "SLSA_PROVENANCE_LINK_OK=${SLSA_PROVENANCE_LINK_OK}"
}
trap cleanup EXIT

fail(){
  echo "FAIL: slsa_provenance_min ${1}"
  exit 1
}

command -v node >/dev/null 2>&1 || fail "node_not_found"

TOP="$(git rev-parse --show-toplevel)"
PROV_FILE="${TOP}/.artifacts/slsa_provenance_min.json"
RUN_URL_EXPECTED="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-<repo>}/actions/runs/${GITHUB_RUN_ID:-0}"

# 1) 존재
[[ -f "$PROV_FILE" ]] || fail "provenance_file_missing=${PROV_FILE}"
SLSA_PROVENANCE_PRESENT_OK=1

# 2) 형식(기계 판정)
node <<'NODE'
const fs = require('fs');

const p = process.env.PROV_FILE || `${process.cwd()}/.artifacts/slsa_provenance_min.json`;
const raw = fs.readFileSync(p, 'utf8');
const obj = JSON.parse(raw);

function req(path, cond){
  if(!cond) throw new Error(`missing_or_invalid:${path}`);
}

req('_type', typeof obj._type === 'string' && obj._type.length > 0);
req('subject', Array.isArray(obj.subject));
req('predicateType', typeof obj.predicateType === 'string' && obj.predicateType.length > 0);
req('predicate', typeof obj.predicate === 'object' && obj.predicate);

req('predicate.buildType', typeof obj.predicate.buildType === 'string' && obj.predicate.buildType.length > 0);
req('predicate.builder', typeof obj.predicate.builder === 'object' && obj.predicate.builder);
req('predicate.builder.id', typeof obj.predicate.builder.id === 'string' && obj.predicate.builder.id.length > 0);

req('predicate.invocation', typeof obj.predicate.invocation === 'object' && obj.predicate.invocation);
req('predicate.invocation.parameters', typeof obj.predicate.invocation.parameters === 'object' && obj.predicate.invocation.parameters);

req('predicate.metadata', typeof obj.predicate.metadata === 'object' && obj.predicate.metadata);
req('predicate.metadata.buildStartedOn', typeof obj.predicate.metadata.buildStartedOn === 'string');
req('predicate.metadata.buildFinishedOn', typeof obj.predicate.metadata.buildFinishedOn === 'string');

req('predicate.materials', Array.isArray(obj.predicate.materials));
if (obj.predicate.materials.length > 0) {
  const m0 = obj.predicate.materials[0];
  req('predicate.materials[0].uri', typeof m0.uri === 'string' && m0.uri.length > 0);
  req('predicate.materials[0].digest.sha256', typeof (m0.digest||{}).sha256 === 'string' && (m0.digest.sha256||'').length > 0);
}

process.exit(0);
NODE

SLSA_PROVENANCE_FORMAT_OK=1

# 3) 링크(run URL) 고정
# provenance 파일 안의 run_url이 기대값과 같아야 함
node <<NODE
const fs = require('fs');
const obj = JSON.parse(fs.readFileSync("${PROV_FILE}", "utf8"));
const expected = "${RUN_URL_EXPECTED}";
if (!obj.predicate || !obj.predicate.invocation || !obj.predicate.invocation.parameters) process.exit(1);
if (obj.predicate.invocation.parameters.run_url !== expected) process.exit(1);
process.exit(0);
NODE

SLSA_PROVENANCE_LINK_OK=1
exit 0

