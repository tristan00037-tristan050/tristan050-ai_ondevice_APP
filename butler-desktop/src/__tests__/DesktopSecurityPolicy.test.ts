import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';


describe('desktop least-privilege policy', () => {
  it('forbids inline scripts and constrains active content', () => {
    const config = JSON.parse(readFileSync(resolve(process.cwd(), 'src-tauri/tauri.conf.json'), 'utf8')) as {
      app: { security: { csp: string } };
    };
    const csp = config.app.security.csp;
    expect(csp).toContain("script-src 'self'");
    expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'none'");
  });

  it('keeps file writes outside the webview capability surface', () => {
    const capability = JSON.parse(
      readFileSync(resolve(process.cwd(), 'src-tauri/capabilities/default.json'), 'utf8'),
    ) as { permissions: Array<string | object> };
    expect(capability.permissions).not.toContain('dialog:allow-save');
    expect(capability.permissions).not.toContain('fs:allow-write-file');
    expect(capability.permissions.filter(value => typeof value === 'string' && value.includes('recursive'))).toEqual([]);
  });
});
