'use strict';

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

function sha256File(filePath: string): string {
  const h = crypto.createHash('sha256');
  const fd = fs.openSync(filePath, 'r');
  const buf = Buffer.alloc(1024 * 1024);
  try {
    while (true) {
      const bytesRead = fs.readSync(fd, buf, 0, buf.length, null);
      if (bytesRead === 0) break;
      h.update(buf.subarray(0, bytesRead));
    }
  } finally {
    fs.closeSync(fd);
  }
  return h.digest('hex');
}

export function writeSha256SumsV1(packDir: string, files: string[]): void {
  const lines: string[] = [];
  for (const rel of files) {
    const abs = path.join(packDir, rel);
    if (!fs.existsSync(abs)) {
      throw new Error(`SHA256SUMS_SOURCE_FILE_MISSING:${rel}`);
    }
    lines.push(`${sha256File(abs)}  ${rel}`);
  }
  fs.writeFileSync(path.join(packDir, 'SHA256SUMS'), lines.join('\n') + '\n', 'utf8');
}
