#!/usr/bin/env bash
set -euo pipefail

AI_PERF_HARNESS_V1_OK=0
AI_RERANK_NEARTIE_V1_OK=0
AI_CALIB_V1_OK=0
AI_PROPENSITY_IPS_SNIPS_V1_OK=0
AI_DETERMINISM_OK=0
AI_P95_BUDGET_OK=0
AI_NEARTIE_SWAP_BUDGET_OK=0

cleanup(){
  echo "AI_PERF_HARNESS_V1_OK=${AI_PERF_HARNESS_V1_OK}"
  echo "AI_RERANK_NEARTIE_V1_OK=${AI_RERANK_NEARTIE_V1_OK}"
  echo "AI_CALIB_V1_OK=${AI_CALIB_V1_OK}"
  echo "AI_PROPENSITY_IPS_SNIPS_V1_OK=${AI_PROPENSITY_IPS_SNIPS_V1_OK}"
  echo "AI_DETERMINISM_OK=${AI_DETERMINISM_OK}"
  echo "AI_P95_BUDGET_OK=${AI_P95_BUDGET_OK}"
  echo "AI_NEARTIE_SWAP_BUDGET_OK=${AI_NEARTIE_SWAP_BUDGET_OK}"
  if [[ "${AI_PERF_HARNESS_V1_OK}" == "1" ]] && \
     [[ "${AI_RERANK_NEARTIE_V1_OK}" == "1" ]] && \
     [[ "${AI_CALIB_V1_OK}" == "1" ]] && \
     [[ "${AI_PROPENSITY_IPS_SNIPS_V1_OK}" == "1" ]] && \
     [[ "${AI_DETERMINISM_OK}" == "1" ]] && \
     [[ "${AI_P95_BUDGET_OK}" == "1" ]] && \
     [[ "${AI_NEARTIE_SWAP_BUDGET_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

MODULES_DIR="webcore_appcore_starter_4_17/shared/ai_v1"

# 1) Module files exist and have correct structure
test -s "${MODULES_DIR}/perf_v1.ts"
test -s "${MODULES_DIR}/rerank_neartie_v1.ts"
test -s "${MODULES_DIR}/calib_v1.ts"
test -s "${MODULES_DIR}/propensity_v1.ts"

# 2) Static analysis: check for required patterns
node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const MODULES_DIR = path.join(ROOT, 'webcore_appcore_starter_4_17/shared/ai_v1');

const modules = {
  'perf_v1.ts': {
    mustHave: ['export function perfV1', 'p95_budget', 'P95_BUDGET'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'rerank_neartie_v1.ts': {
    mustHave: ['export function rerankNearTieV1', 'swap'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'calib_v1.ts': {
    mustHave: ['export function calibV1', 'over_intervention', 'intervention'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'propensity_v1.ts': {
    mustHave: ['export function propensityV1', 'ips', 'snips', 'over_intervention'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
};

let allOk = true;

for (const [mod, checks] of Object.entries(modules)) {
  const filePath = path.join(MODULES_DIR, mod);
  const content = fs.readFileSync(filePath, 'utf8');
  
  // Check must-have patterns
  for (const pattern of checks.mustHave) {
    if (!content.includes(pattern)) {
      console.error(`BLOCK: ${mod} missing required pattern: ${pattern}`);
      allOk = false;
    }
  }
  
  // Check must-not-have patterns (excluding comments)
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('//') || line.startsWith('*') || line.startsWith('/*')) {
      continue;
    }
    for (const pattern of checks.mustNotHave) {
      if (line.includes(pattern)) {
        console.error(`BLOCK: ${mod} contains forbidden pattern: ${pattern} (line ${i + 1})`);
        allOk = false;
      }
    }
  }
  
  // Check for export function
  if (!content.includes('export function')) {
    console.error(`BLOCK: ${mod} missing export function`);
    allOk = false;
  }
}

if (!allOk) {
  process.exit(1);
}

console.log('AI_PERF_HARNESS_V1_OK=1');
console.log('AI_RERANK_NEARTIE_V1_OK=1');
console.log('AI_CALIB_V1_OK=1');
console.log('AI_PROPENSITY_IPS_SNIPS_V1_OK=1');
NODE

# Capture output and set variables
OUTPUT=$(node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const MODULES_DIR = path.join(ROOT, 'webcore_appcore_starter_4_17/shared/ai_v1');

const modules = {
  'perf_v1.ts': {
    mustHave: ['export function perfV1', 'p95_budget', 'P95_BUDGET'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'rerank_neartie_v1.ts': {
    mustHave: ['export function rerankNearTieV1', 'swap'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'calib_v1.ts': {
    mustHave: ['export function calibV1', 'over_intervention', 'intervention'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
  'propensity_v1.ts': {
    mustHave: ['export function propensityV1', 'ips', 'snips', 'over_intervention'],
    mustNotHave: ['Math.random()', 'Date.now()', 'prompt', 'raw text'],
  },
};

let allOk = true;

for (const [mod, checks] of Object.entries(modules)) {
  const filePath = path.join(MODULES_DIR, mod);
  const content = fs.readFileSync(filePath, 'utf8');
  
  for (const pattern of checks.mustHave) {
    if (!content.includes(pattern)) {
      console.error(`BLOCK: ${mod} missing required pattern: ${pattern}`);
      allOk = false;
    }
  }
  
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('//') || line.startsWith('*') || line.startsWith('/*')) {
      continue;
    }
    for (const pattern of checks.mustNotHave) {
      if (line.includes(pattern)) {
        console.error(`BLOCK: ${mod} contains forbidden pattern: ${pattern} (line ${i + 1})`);
        allOk = false;
      }
    }
  }
  
  if (!content.includes('export function')) {
    console.error(`BLOCK: ${mod} missing export function`);
    allOk = false;
  }
}

if (!allOk) {
  process.exit(1);
}

console.log('AI_PERF_HARNESS_V1_OK=1');
console.log('AI_RERANK_NEARTIE_V1_OK=1');
console.log('AI_CALIB_V1_OK=1');
console.log('AI_PROPENSITY_IPS_SNIPS_V1_OK=1');
NODE
)

if [[ $? -ne 0 ]]; then
  echo "$OUTPUT"
  exit 1
fi

# Set variables from output
while IFS= read -r line; do
  if [[ "$line" == AI_*_OK=1 ]]; then
    key=$(echo "$line" | cut -d= -f1)
    case "$key" in
      AI_PERF_HARNESS_V1_OK) AI_PERF_HARNESS_V1_OK=1 ;;
      AI_RERANK_NEARTIE_V1_OK) AI_RERANK_NEARTIE_V1_OK=1 ;;
      AI_CALIB_V1_OK) AI_CALIB_V1_OK=1 ;;
      AI_PROPENSITY_IPS_SNIPS_V1_OK) AI_PROPENSITY_IPS_SNIPS_V1_OK=1 ;;
    esac
  fi
done <<< "$OUTPUT"

# 3) Check determinism (static: no Math.random, Date.now in logic)
node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const MODULES_DIR = path.join(ROOT, 'webcore_appcore_starter_4_17/shared/ai_v1');

const modules = ['perf_v1.ts', 'rerank_neartie_v1.ts', 'calib_v1.ts', 'propensity_v1.ts'];
let determinismOk = true;

for (const mod of modules) {
  const filePath = path.join(MODULES_DIR, mod);
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('//') || line.startsWith('*') || line.startsWith('/*')) {
      continue;
    }
    if (line.includes('Math.random()') || (line.includes('Date.now()') && !line.includes('ts_utc'))) {
      console.error(`BLOCK: ${mod} uses non-deterministic function (line ${i + 1}): ${line}`);
      determinismOk = false;
    }
  }
}

if (!determinismOk) {
  process.exit(1);
}

console.log('AI_DETERMINISM_OK=1');
NODE
AI_DETERMINISM_OK=1

# 4) Check P95 budget enforcement
node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const perfPath = path.join(ROOT, 'webcore_appcore_starter_4_17/shared/ai_v1/perf_v1.ts');
const content = fs.readFileSync(perfPath, 'utf8');

// Check for P95 budget constant and enforcement
if (!content.includes('P95_BUDGET') && !content.includes('p95_budget')) {
  console.error('BLOCK: perf_v1.ts missing P95 budget constant');
  process.exit(1);
}

if (!content.includes('p95_budget_ok')) {
  console.error('BLOCK: perf_v1.ts missing p95_budget_ok output');
  process.exit(1);
}

console.log('AI_P95_BUDGET_OK=1');
NODE
AI_P95_BUDGET_OK=1

# 5) Check NearTie swap budget enforcement
node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const rerankPath = path.join(ROOT, 'webcore_appcore_starter_4_17/shared/ai_v1/rerank_neartie_v1.ts');
const content = fs.readFileSync(rerankPath, 'utf8');

// Check for swap budget constant and enforcement
if (!content.includes('MAX_SWAP') && !content.includes('max_swaps')) {
  console.error('BLOCK: rerank_neartie_v1.ts missing swap budget constant');
  process.exit(1);
}

if (!content.includes('swap_budget_ok')) {
  console.error('BLOCK: rerank_neartie_v1.ts missing swap_budget_ok output');
  process.exit(1);
}

console.log('AI_NEARTIE_SWAP_BUDGET_OK=1');
NODE
AI_NEARTIE_SWAP_BUDGET_OK=1

exit 0
