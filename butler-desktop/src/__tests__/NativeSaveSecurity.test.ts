import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInvoke } = vi.hoisted(() => ({ mockInvoke: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ invoke: mockInvoke }));

import { saveExportFile } from '../lib/nativeSave';


describe('native user-selected export boundary', () => {
  beforeEach(() => {
    mockInvoke.mockReset();
    mockInvoke.mockResolvedValue(true);
  });

  it('sends bytes to the single native save command without accepting a path', async () => {
    await expect(saveExportFile('butler_result.xlsx', 'xlsx', new Uint8Array([1, 2, 3]))).resolves.toBe(true);
    expect(mockInvoke).toHaveBeenCalledWith('save_export_file', new Uint8Array([1, 2, 3]), {
      headers: {
        'butler-export-name': 'butler_result.xlsx',
        'butler-export-extension': 'xlsx',
      },
    });
  });

  it.each([
    ['../escape.md', 'md', new Uint8Array([1])],
    ['wrong.docx', 'md', new Uint8Array([1])],
    ['empty.md', 'md', new Uint8Array()],
  ] as const)('rejects an invalid export request before IPC', async (name, extension, bytes) => {
    await expect(saveExportFile(name, extension, bytes)).rejects.toThrow('NATIVE_EXPORT_REQUEST_INVALID');
    expect(mockInvoke).not.toHaveBeenCalled();
  });
});
