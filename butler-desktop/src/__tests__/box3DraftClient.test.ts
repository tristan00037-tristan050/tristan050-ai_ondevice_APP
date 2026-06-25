import { describe, expect, it, vi } from 'vitest';
import { createBox3Draft, validateBox3DraftRequest } from '../lib/box3/box3DraftClient';

describe('box3DraftClient', () => {
  it('validates reference docs and drafting request', () => {
    expect(validateBox3DraftRequest({ reference_docs: [], drafting_request: '', format_hint: '자유형' })).toContain('REFERENCE_DOCS_REQUIRED');
  });

  it('posts reference_docs + drafting_request to /v1/cards/3/draft', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(_input)).toContain('/v1/cards/3/draft');
      const body = JSON.parse(String(init?.body));
      expect(body.reference_docs).toEqual(['과거 문서']);
      expect(body.drafting_request).toBe('새 초안');
      return new Response(JSON.stringify({ draft: '초안', raw_doc_logged: false }), { status: 200 });
    });
    const result = await createBox3Draft(
      { reference_docs: ['과거 문서'], drafting_request: '새 초안', format_hint: '자유형' },
      { fetcher: fetcher as unknown as typeof fetch },
    );
    expect(result.draft).toBe('초안');
  });
});
