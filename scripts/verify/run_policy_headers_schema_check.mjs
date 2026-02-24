#!/usr/bin/env node
/**
 * POLICY_HEADERS_SCHEMA_V1: Run bff-accounting policy loader (loadPolicies).
 * Meta-only: success prints POLICY_HEADERS_SCHEMA_V1_OK=1, POLICY_HEADERS_RULE_DESCRIPTION_PRESENT_OK=1.
 * Failure: exit 1 (loader logs to stderr; do not dump content).
 * Run from repo root. Requires: npm run build:packages:server (dist) in webcore_appcore_starter_4_17.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const loaderPath = join(process.cwd(), 'webcore_appcore_starter_4_17', 'packages', 'bff-accounting', 'dist', 'policy', 'loader.js');
const loaderUrl = pathToFileURL(loaderPath).href;

const { loadPolicies, getHeadersPolicy, getExportPolicy, getMetaOnlyPolicy } = await import(loaderUrl);
loadPolicies();

if (!getHeadersPolicy() || !getExportPolicy() || !getMetaOnlyPolicy()) {
  process.exitCode = 1;
  process.exit(1);
}

console.log('POLICY_HEADERS_SCHEMA_V1_OK=1');
console.log('POLICY_HEADERS_RULE_DESCRIPTION_PRESENT_OK=1');
