#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = process.env.GIT_ROOT || path.resolve(__dirname, '..', '..');

function parseArgs() {
  const args = process.argv.slice(2);
  let ssot = path.join(ROOT, 'docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt');
  let declared = path.join(ROOT, 'tools/mcp_gateway/CAPABILITIES_DECLARED_V1.txt');
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--ssot' && args[i + 1]) { ssot = args[i + 1]; i++; }
    else if (args[i] === '--declared' && args[i + 1]) { declared = args[i + 1]; i++; }
  }
  return { ssot, declared };
}

function extractAllowCapability(filePath) {
  if (!fs.existsSync(filePath)) return null;
  const content = fs.readFileSync(filePath, 'utf8');
  return content.split('\n')
    .filter(l => l.startsWith('ALLOW_CAPABILITY='))
    .map(l => l.replace(/^ALLOW_CAPABILITY=/, '').trim())
    .filter(Boolean);
}

function main() {
  const { ssot, declared } = parseArgs();

  if (!fs.existsSync(ssot)) {
    process.exitCode = 1;
    process.exit(1);
  }
  const ssotContent = fs.readFileSync(ssot, 'utf8');
  if (!ssotContent.includes('MCP_CAPABILITIES_SSOT_V1_TOKEN=1')) {
    process.exitCode = 1;
    process.exit(1);
  }
  const ssotSet = new Set(extractAllowCapability(ssot));
  if (ssotSet.size === 0) {
    process.exitCode = 1;
    process.exit(1);
  }

  if (!fs.existsSync(declared)) {
    process.exitCode = 1;
    process.exit(1);
  }
  const declaredContent = fs.readFileSync(declared, 'utf8');
  if (!declaredContent.includes('MCP_GATEWAY_CAPABILITIES_DECLARED_V1_TOKEN=1')) {
    process.exitCode = 1;
    process.exit(1);
  }
  const declaredList = extractAllowCapability(declared);
  if (declaredList.length === 0) {
    process.exitCode = 1;
    process.exit(1);
  }

  for (const cap of declaredList) {
    if (!ssotSet.has(cap)) {
      console.log('ERROR_CODE=CAPABILITY_NOT_ALLOWED');
      console.log('HIT_CAPABILITY=' + cap);
      process.exitCode = 1;
      process.exit(1);
    }
  }

  process.exit(0);
}

main();
