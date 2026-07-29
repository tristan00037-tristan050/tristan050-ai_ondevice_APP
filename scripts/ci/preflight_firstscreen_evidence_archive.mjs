#!/usr/bin/env node
import { preflightZipFile } from './evidence_archive.mjs';

const path = process.argv[2];
if (!path) {
  console.log('EVIDENCE_ARCHIVE_PREFLIGHT_OK=0');
  console.log('ERROR_CODE=ARGUMENT_INVALID');
  process.exit(2);
}
try {
  await preflightZipFile(path);
  console.log('EVIDENCE_ARCHIVE_PREFLIGHT_OK=1');
} catch (error) {
  console.log('EVIDENCE_ARCHIVE_PREFLIGHT_OK=0');
  console.log(`ERROR_CODE=${error.message}`);
  process.exit(1);
}
