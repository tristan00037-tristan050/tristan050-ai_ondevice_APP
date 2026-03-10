'use strict';

import fs from 'node:fs';
import path from 'node:path';
import type { RuntimeManifestV1 } from './runtime_manifest_builder_v1';

export function writeRuntimeManifestJsonV1(
  packDir: string,
  manifest: RuntimeManifestV1
): void {
  const out = path.join(packDir, 'runtime_manifest.json');
  fs.mkdirSync(packDir, { recursive: true });
  fs.writeFileSync(out, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
}
