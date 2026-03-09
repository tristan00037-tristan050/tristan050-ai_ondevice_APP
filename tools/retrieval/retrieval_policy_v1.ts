'use strict';

export interface RetrievalResult {
  id: string;
  snippet: string;
  score: number;
  [key: string]: unknown;
}

export interface FilterOptions {
  maxResults?: number;
  maxSnippetLength?: number;
  forbiddenKeys?: string[];
}

export interface FilterOutput {
  results: RetrievalResult[];
  digest: string;
  filtered_count: number;
}

const FORBIDDEN_KEYS_DEFAULT: string[] = [];
const MAX_RESULTS_DEFAULT = 20;
const MAX_SNIPPET_LENGTH_DEFAULT = 512;

function sha256Hex(input: string): string {
  // Browser/Node-agnostic: use a simple deterministic hash for policy digest
  // In production, replace with crypto.subtle or node:crypto
  let h = 0;
  for (let i = 0; i < input.length; i++) {
    h = (Math.imul(31, h) + input.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}

export function filterRetrievalResults(
  raw: unknown,
  opts: FilterOptions = {}
): FilterOutput {
  if (!Array.isArray(raw)) {
    throw new TypeError('retrieval results must be an array');
  }

  const maxResults = opts.maxResults ?? MAX_RESULTS_DEFAULT;
  const maxSnippetLength = opts.maxSnippetLength ?? MAX_SNIPPET_LENGTH_DEFAULT;
  const forbiddenKeys = opts.forbiddenKeys ?? FORBIDDEN_KEYS_DEFAULT;

  const results: RetrievalResult[] = [];

  for (const item of raw) {
    if (typeof item !== 'object' || item === null) continue;
    const record = item as Record<string, unknown>;

    // Check for forbidden keys
    const hasForbidden = forbiddenKeys.some((k) => k in record);
    if (hasForbidden) continue;

    if (typeof record['id'] !== 'string') continue;
    if (typeof record['snippet'] !== 'string') continue;
    if (typeof record['score'] !== 'number') continue;

    const snippet =
      record['snippet'].length > maxSnippetLength
        ? record['snippet'].slice(0, maxSnippetLength)
        : record['snippet'];

    results.push({
      ...(record as RetrievalResult),
      snippet,
    });

    if (results.length >= maxResults) break;
  }

  const digest = sha256Hex(JSON.stringify(results));

  return {
    results,
    digest,
    filtered_count: (raw as unknown[]).length - results.length,
  };
}
