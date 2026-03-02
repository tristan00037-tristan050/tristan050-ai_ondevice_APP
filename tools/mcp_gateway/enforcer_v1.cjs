#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = process.env.GIT_ROOT || path.resolve(__dirname, '../..');
const SSOT = path.join(ROOT, 'docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt');

if (!fs.existsSync(SSOT)) {
  process.exitCode = 1;
  process.exit(1);
}
const content = fs.readFileSync(SSOT, 'utf8');
if (!content.includes('MCP_CAPABILITIES_SSOT_V1_TOKEN=1')) {
  process.exitCode = 1;
  process.exit(1);
}
const allowed = content.split('\n')
  .filter(l => l.startsWith('ALLOW_CAPABILITY='))
  .map(l => l.replace(/^ALLOW_CAPABILITY=/, '').trim())
  .filter(Boolean);
if (allowed.length === 0) {
  process.exitCode = 1;
  process.exit(1);
}
process.exit(0);
