import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { parseAnalyzeStreamResult } from '../lib/cards/analyzeStreamResult';
import { MAX_BYTES_PER_CHAR, MAX_CHARS_PER_FILE, prepareCardTextFiles } from '../lib/cards/fileText';
import { validateBox4DocumentReviewResult } from '../lib/box4/box4ReviewClient';
import { hasBox6SecretAutofill, validateBox6FormFillResult } from '../lib/box6/box6FormFillClient';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: async (command: string) =>
    command === 'get_sidecar_capability_token' ? 'test-capability-token' : undefined,
}));

const legacySourceKey = ['source', 'excerpt'].join('_');

const box6Payload = {
  schema_version: 'card_06.form_fill.v1',
  filled_form: '상호: 주식회사 합성\nAPI key: ___',
  field_mappings: [
    {
      target_label: '상호',
      output_value: '주식회사 합성',
      confidence: 'HIGH',
      source_ref: 'our_data.company_name',
      reason_code: 'LABEL_EXACT_MATCH',
    },
    {
      target_label: 'API key',
      output_value: '',
      confidence: 'UNFILLED',
      source_ref: '',
      reason_code: 'FORBIDDEN_SECRET_FIELD',
    },
  ],
  unfilled_fields: ['API key'],
  review_required: true,
  warnings: ['secret/security 필드는 자동기입하지 않았습니다.'],
};

const unsafeBox6SecretPayload = {
  ...box6Payload,
  filled_form: '상호: 주식회사 합성\nAPI key: sk-test-secret-value-123456',
  field_mappings: [
    box6Payload.field_mappings[0],
    {
      target_label: 'API key',
      output_value: 'sk-test-secret-value-123456',
      confidence: 'HIGH',
      source_ref: 'our_data.api_key',
      reason_code: 'LABEL_EXACT_MATCH',
    },
  ],
  unfilled_fields: [],
  review_required: false,
  warnings: [],
};

const box4Payload = {
  schema_version: 'card_04.document_review.v1',
  issues: [
    {
      location: '1문단',
      issue_type: 'STYLE',
      original_text: '검토할 첨부 문서 초안입니다.',
      suggestion: '문장을 더 명확하게 다듬으세요.',
      confidence: 'HIGH',
    },
  ],
  overall_score: 82,
  summary: '문체 보완 사항이 있습니다.',
  review_required: true,
  warnings: [],
  raw_log_zero: true,
  external_send_zero: true,
};

const box4NoIssuesPayload = {
  schema_version: 'card_04.document_review.v1',
  issues: [],
  overall_score: 100,
  summary: '추가 지적 사항이 없습니다.',
  review_required: false,
  warnings: [],
  raw_log_zero: true,
  external_send_zero: true,
};

const unsafeBox4SecretPayload = {
  ...box4Payload,
  issues: [
    {
      ...box4Payload.issues[0],
      original_text: 'api key: sk-test-secret-value-123456',
      suggestion: '문서에서 api key: sk-test-secret-value-123456 값을 제거하세요.',
    },
  ],
};

function completeSse(payload: unknown): string {
  return `event: meta\ndata: {"source":"test"}\n\nevent: complete\ndata: ${JSON.stringify({
    result_text: JSON.stringify(payload),
  })}\n\n`;
}

function makeFetchMock(payloads: { box6?: unknown; box4?: unknown } = {}) {
  return vi.fn().mockImplementation((url: string | URL | Request, init?: RequestInit) => {
    if (String(url).includes('/health')) {
      return Promise.resolve(
        new Response(JSON.stringify({ status: 'ok', version: '0.9.0' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      );
    }
    if (String(url).includes('/api/analyze/stream')) {
      const body = init?.body as FormData | undefined;
      const mode = body?.get('card_mode');
      const payload = mode === '6' ? payloads.box6 ?? box6Payload : payloads.box4 ?? box4Payload;
      return Promise.resolve(new Response(completeSse(payload), { status: 200 }));
    }
    return Promise.resolve(new Response('', { status: 404 }));
  });
}

async function loadApp() {
  vi.resetModules();
  vi.stubEnv('VITE_BUTLER_BOX4_DOCUMENT_REVIEW', '1');
  vi.stubEnv('VITE_BUTLER_BOX6_FORM_FILL', '1');
  return import('../App');
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('Box4/Box6 analyze stream parser', () => {
  it('prefers the last valid SSE JSON and parses nested result_text', () => {
    const body = `event: complete\ndata: {"result_text":"not json"}\n\n${completeSse(box6Payload)}`;
    const parsed = parseAnalyzeStreamResult(body, validateBox6FormFillResult);

    expect(parsed.schema_version).toBe('card_06.form_fill.v1');
    expect(parsed.field_mappings[1].confidence).toBe('UNFILLED');
    expect(parsed.field_mappings[0].source_ref).toBe('our_data.company_name');
    expect(parsed.review_required).toBe(true);
  });

  it('accepts fenced JSON and rejects invalid Box4 enums fail-safe', () => {
    const fenced = `\`\`\`json\n${JSON.stringify(box4NoIssuesPayload)}\n\`\`\``;
    expect(parseAnalyzeStreamResult(fenced, validateBox4DocumentReviewResult).issues).toHaveLength(0);

    const invalid = {
      ...box4Payload,
      issues: [{ ...box4Payload.issues[0], issue_type: 'SECURITY' }],
    };
    expect(() => parseAnalyzeStreamResult(JSON.stringify(invalid), validateBox4DocumentReviewResult)).toThrow(
      '결과 형식을 확인하지 못했습니다.'
    );
  });

  it('rejects Box6 legacy mapping source field', () => {
    const invalid = {
      ...box6Payload,
      field_mappings: [
        {
          target_label: '상호',
          output_value: '주식회사 합성',
          confidence: 'HIGH',
          [legacySourceKey]: 'legacy field',
          reason_code: 'LABEL_EXACT_MATCH',
        },
      ],
    };

    expect(() => parseAnalyzeStreamResult(JSON.stringify(invalid), validateBox6FormFillResult)).toThrow(
      'BOX6_LEGACY_MAPPING_SCHEMA'
    );
  });

  it('rejects Box6 mapping-level review flag and requires top-level review flag', () => {
    const mappingLevelReview = {
      ...box6Payload,
      field_mappings: [{ ...box6Payload.field_mappings[0], review_required: false }],
    };
    expect(() => parseAnalyzeStreamResult(JSON.stringify(mappingLevelReview), validateBox6FormFillResult)).toThrow(
      'BOX6_LEGACY_MAPPING_SCHEMA'
    );

    const missingTopLevelReview = { ...box6Payload } as Record<string, unknown>;
    delete missingTopLevelReview.review_required;
    expect(() => parseAnalyzeStreamResult(JSON.stringify(missingTopLevelReview), validateBox6FormFillResult)).toThrow(
      '결과 형식을 확인하지 못했습니다.'
    );
  });

  it('allows reviewed secret placeholders and flags secret reason autofill', () => {
    const reviewedSecret = {
      ...box6Payload,
      field_mappings: [
        {
          target_label: '인증 정보',
          output_value: '',
          confidence: 'UNFILLED',
          source_ref: '',
          reason_code: 'FORBIDDEN_SECRET_FIELD',
        },
      ],
      unfilled_fields: ['인증 정보'],
      review_required: false,
    };
    const parsedReviewedSecret = parseAnalyzeStreamResult(JSON.stringify(reviewedSecret), validateBox6FormFillResult);
    expect(hasBox6SecretAutofill(parsedReviewedSecret)).toBe(false);

    const unsafeSecret = {
      ...reviewedSecret,
      field_mappings: [
        {
          ...reviewedSecret.field_mappings[0],
          output_value: '관리자1234',
          confidence: 'HIGH',
        },
      ],
      unfilled_fields: [],
    };
    const parsedUnsafeSecret = parseAnalyzeStreamResult(JSON.stringify(unsafeSecret), validateBox6FormFillResult);
    expect(hasBox6SecretAutofill(parsedUnsafeSecret)).toBe(true);
  });
});

describe('Box4/Box6 file limits', () => {
  it('keeps only allowed text files and truncates without exposing content preview', async () => {
    const longText = '가'.repeat(25000);
    const result = await prepareCardTextFiles([
      new File([longText], 'data.txt', { type: 'text/plain' }),
      new File(['%PDF-1.7'], 'contract.pdf', { type: 'application/pdf' }),
    ]);

    expect(result.files).toHaveLength(1);
    expect(result.files[0].chars).toBe(20000);
    expect(result.files[0].truncated).toBe(true);
    expect(result.rejected[0]).toMatchObject({ name: 'contract.pdf', reason: 'unsupported_type' });
  });

  it('enforces the five-file cap before analyze stream submission', async () => {
    const result = await prepareCardTextFiles(
      Array.from({ length: 6 }, (_, index) => new File([`내용 ${index}`], `doc-${index}.txt`, { type: 'text/plain' }))
    );

    expect(result.files).toHaveLength(5);
    expect(result.rejected[0]).toMatchObject({ name: 'doc-5.txt', reason: 'too_many' });
  });

  it('slices large allowed files before reading text', async () => {
    const originalText = vi.fn(async () => 'SHOULD_NOT_READ_ORIGINAL');
    const slicedText = vi.fn(async () => 'x'.repeat(MAX_CHARS_PER_FILE + 5000));
    const slicedBlob = { text: slicedText } as unknown as Blob;
    const slice = vi.fn(() => slicedBlob);
    const file = {
      name: 'large-export.csv',
      size: 100000,
      type: 'text/csv',
      lastModified: 0,
      text: originalText,
      slice,
    } as unknown as File;

    const result = await prepareCardTextFiles([file]);

    expect(slice).toHaveBeenCalledWith(0, MAX_CHARS_PER_FILE * MAX_BYTES_PER_CHAR);
    expect(originalText).not.toHaveBeenCalled();
    expect(slicedText).toHaveBeenCalled();
    expect(result.files[0].chars).toBe(MAX_CHARS_PER_FILE);
    expect(result.files[0].truncated).toBe(true);
  });
});

describe('Box4/Box6 frontend modals', () => {
  it('opens Box6 modal and submits to analyze stream with card_mode 6', async () => {
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);
    const { App } = await loadApp();

    render(<App />);

    await waitFor(() => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument());
    fireEvent.click(screen.getByTestId('card-6'));
    expect(screen.getByTestId('box6-form-fill-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('box6-blank-form-input'), {
      target: { value: '상호: ___\nAPI key: ___' },
    });
    fireEvent.change(screen.getByTestId('box6-file-input'), {
      target: { files: [new File(['상호: 주식회사 합성'], 'company.txt', { type: 'text/plain' })] },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('box6-submit-btn'));
    });

    await waitFor(() => expect(screen.getByTestId('box6-result')).toBeInTheDocument());
    expect(screen.getByText('our_data.company_name')).toBeInTheDocument();
    expect(screen.getByText('미기입')).toBeInTheDocument();
    expect(screen.getByText('검토 필요')).toBeInTheDocument();
    const streamCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/api/analyze/stream'));
    expect(streamCall).toBeDefined();
    const body = (streamCall![1] as RequestInit).body as FormData;
    expect(body.get('card_mode')).toBe('6');
    expect(body.get('file_count')).toBe('1');
    expect(body.get('file_0')).toBeInstanceOf(File);
    expect(body.get('files')).toBeNull();
    expect((streamCall![1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer test-capability-token' });
  });

  it('blocks secret-labeled Box6 autofill before rendering returned values', async () => {
    const fetchMock = makeFetchMock({ box6: unsafeBox6SecretPayload });
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);
    const { App } = await loadApp();

    render(<App />);

    await waitFor(() => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument());
    fireEvent.click(screen.getByTestId('card-6'));
    fireEvent.change(screen.getByTestId('box6-blank-form-input'), {
      target: { value: '상호: ___\nAPI key: ___' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('box6-submit-btn'));
    });

    await waitFor(() =>
      expect(screen.getByTestId('box6-error')).toHaveTextContent('보안 항목 자동기입이 감지되어 결과를 표시하지 않았습니다.')
    );
    expect(screen.queryByTestId('box6-result')).not.toBeInTheDocument();
    expect(screen.queryByText('sk-test-secret-value-123456')).not.toBeInTheDocument();
  });

  it('blocks Box4 secret text before rendering returned issues', async () => {
    const fetchMock = makeFetchMock({ box4: unsafeBox4SecretPayload });
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);
    const { App } = await loadApp();

    render(<App />);

    await waitFor(() => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument());
    fireEvent.click(screen.getByTestId('card-4'));
    fireEvent.change(screen.getByTestId('box4-target-document-input'), {
      target: { value: '검토할 첨부 문서 초안입니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('box4-submit-btn'));
    });

    await waitFor(() =>
      expect(screen.getByTestId('box4-error')).toHaveTextContent('민감정보가 포함되어 결과를 표시하지 않았습니다.')
    );
    expect(screen.queryByTestId('box4-result')).not.toBeInTheDocument();
    expect(screen.queryByText('sk-test-secret-value-123456')).not.toBeInTheDocument();
  });

  it('opens Box4 modal, traps focus, submits card_mode 4, and closes with Escape returning focus', async () => {
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);
    const { App } = await loadApp();

    render(<App />);

    await waitFor(() => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument());
    const card4 = screen.getByTestId('card-4');
    card4.focus();
    fireEvent.click(card4);
    expect(screen.getByTestId('box4-document-review-modal')).toBeInTheDocument();
    expect(document.querySelector('[inert]')).not.toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { name: '첨부 문서 수정·보완' })));

    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    closeButtons[0].focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(closeButtons[1]);
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(closeButtons[0]);

    fireEvent.change(screen.getByTestId('box4-target-document-input'), {
      target: { value: '검토할 첨부 문서 초안입니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('box4-submit-btn'));
    });

    await waitFor(() => expect(screen.getByTestId('box4-result')).toBeInTheDocument());
    const streamCall = fetchMock.mock.calls.find(([url, init]) => {
      if (!String(url).includes('/api/analyze/stream')) return false;
      const body = (init as RequestInit | undefined)?.body;
      return Boolean(body && typeof (body as FormData).get === 'function' && (body as FormData).get('card_mode') === '4');
    });
    expect(streamCall).toBeDefined();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByTestId('box4-document-review-modal')).not.toBeInTheDocument());
    expect(document.activeElement).toBe(card4);
    expect(document.querySelector('[inert]')).toBeNull();
  });
});
