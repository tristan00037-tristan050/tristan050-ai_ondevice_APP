import { invoke } from '@tauri-apps/api/core';

const MAX_EXPORT_BYTES = 64 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(['docx', 'md', 'xlsx']);

export async function saveExportFile(
  suggestedName: string,
  extension: 'docx' | 'md' | 'xlsx',
  bytes: Uint8Array,
): Promise<boolean> {
  if (
    !ALLOWED_EXTENSIONS.has(extension)
    || !suggestedName.endsWith(`.${extension}`)
    || suggestedName.includes('/')
    || suggestedName.includes('\\')
    || bytes.byteLength === 0
    || bytes.byteLength > MAX_EXPORT_BYTES
  ) {
    throw new Error('NATIVE_EXPORT_REQUEST_INVALID');
  }
  const saved = await invoke<boolean>('save_export_file', bytes, {
    headers: {
      'butler-export-name': suggestedName,
      'butler-export-extension': extension,
    },
  });
  return saved === true;
}
