export const MAX_FILES = 5;
export const MAX_CHARS_PER_FILE = 20000;
export const MAX_TOTAL_CHARS = 60000;
export const MAX_BYTES_PER_CHAR = 4;
export const ALLOWED_TEXT_EXT = ['.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.xml', '.html'] as const;

export type PreparedCardFile = {
  file: File;
  name: string;
  size: number;
  chars: number;
  truncated: boolean;
};

export type RejectedCardFile = {
  name: string;
  size: number;
  reason: 'too_many' | 'unsupported_type' | 'empty_total_budget' | 'read_failed';
};

export type PreparedCardFiles = {
  files: PreparedCardFile[];
  rejected: RejectedCardFile[];
  totalChars: number;
};

export function extensionOf(name: string): string {
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index).toLowerCase() : '';
}

export function isAllowedTextFile(file: File): boolean {
  const ext = extensionOf(file.name);
  if (ALLOWED_TEXT_EXT.includes(ext as typeof ALLOWED_TEXT_EXT[number])) return true;
  return Boolean(file.type && (file.type.startsWith('text/') || file.type === 'application/json'));
}

function makeTextFile(original: File, text: string): File {
  return new File([text], original.name, {
    type: original.type || 'text/plain',
    lastModified: original.lastModified,
  });
}

function sliceBlobForRead(file: File, maxChars: number): { blob: Blob; sliced: boolean } {
  const byteLimit = Math.min(file.size, maxChars * MAX_BYTES_PER_CHAR);
  return {
    blob: file.slice(0, byteLimit),
    sliced: byteLimit < file.size,
  };
}

function readBlobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') {
    return blob.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('FILE_READ_FAILED'));
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
    reader.readAsText(blob);
  });
}

export async function prepareCardTextFiles(inputFiles: File[]): Promise<PreparedCardFiles> {
  const files: PreparedCardFile[] = [];
  const rejected: RejectedCardFile[] = [];
  let totalChars = 0;

  for (const [index, file] of inputFiles.entries()) {
    if (index >= MAX_FILES) {
      rejected.push({ name: file.name, size: file.size, reason: 'too_many' });
      continue;
    }
    if (!isAllowedTextFile(file)) {
      rejected.push({ name: file.name, size: file.size, reason: 'unsupported_type' });
      continue;
    }
    if (totalChars >= MAX_TOTAL_CHARS) {
      rejected.push({ name: file.name, size: file.size, reason: 'empty_total_budget' });
      continue;
    }

    try {
      const remaining = MAX_TOTAL_CHARS - totalChars;
      const maxChars = Math.min(MAX_CHARS_PER_FILE, remaining);
      const { blob, sliced } = sliceBlobForRead(file, maxChars);
      const rawText = await readBlobText(blob);
      const text = rawText.slice(0, maxChars);
      const truncated = sliced || rawText.length > text.length;
      totalChars += text.length;
      files.push({
        file: makeTextFile(file, text),
        name: file.name,
        size: file.size,
        chars: text.length,
        truncated,
      });
    } catch {
      rejected.push({ name: file.name, size: file.size, reason: 'read_failed' });
    }
  }

  return { files, rejected, totalChars };
}

export function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
