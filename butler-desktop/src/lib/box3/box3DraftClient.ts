import { sidecarFetch } from '../sidecarFetch';

export type Box3FormatHint = '보고서' | '이메일' | '계약 검토' | '회의 안건' | '자유형';

export type Box3DraftRequest = {
  reference_docs: string[];
  drafting_request: string;
  format_hint: Box3FormatHint;
  max_new_tokens?: number;
};

export type Box3DraftResponse = {
  draft?: string;
  draft_text?: string | null;
  reused_sections?: string[];
  changed_sections?: string[];
  cautions?: string[];
  citations?: Array<Record<string, string>>;
  metrics?: Record<string, unknown>;
  status?: string;
  fail_class?: string | null;
  needs_review?: boolean;
  review_reason_code?: string | null;
  unsupported_claim_count?: number;
  annotated_claim_count?: number;
  label_coverage_ok?: boolean;
  request_digest?: string;
  raw_doc_logged?: false;
  raw_text_logged?: false;
  external_send_zero?: true;
};

export class Box3DraftClientError extends Error {
  readonly status: number;
  readonly failClass: string;

  constructor(message: string, status: number, failClass = 'BOX3_DRAFT_CLIENT_ERROR') {
    super(message);
    this.name = 'Box3DraftClientError';
    this.status = status;
    this.failClass = failClass;
  }
}

function sanitizeFailure(payload: unknown): { failClass: string; message: string } {
  if (typeof payload === 'object' && payload !== null) {
    const record = payload as Record<string, unknown>;
    const detail = typeof record.detail === 'object' && record.detail !== null
      ? (record.detail as Record<string, unknown>)
      : record;
    const failClass = typeof detail.fail_class === 'string' ? detail.fail_class : 'BOX3_DRAFT_BACKEND_ERROR';
    const message = typeof detail.message === 'string' ? detail.message : failClass;
    return { failClass, message };
  }
  return { failClass: 'BOX3_DRAFT_BACKEND_ERROR', message: '박스3 초안 생성에 실패했습니다.' };
}

export function validateBox3DraftRequest(request: Box3DraftRequest): string[] {
  const errors: string[] = [];
  if (!Array.isArray(request.reference_docs) || request.reference_docs.length === 0) {
    errors.push('REFERENCE_DOCS_REQUIRED');
  }
  if (request.reference_docs.length > 5) {
    errors.push('REFERENCE_DOCS_TOO_MANY');
  }
  if (!request.drafting_request.trim()) {
    errors.push('DRAFTING_REQUEST_REQUIRED');
  }
  if (request.drafting_request.length > 2000) {
    errors.push('DRAFTING_REQUEST_TOO_LONG');
  }
  for (const doc of request.reference_docs) {
    if (!doc.trim()) errors.push('REFERENCE_DOC_EMPTY');
    if (doc.length > 20000) errors.push('REFERENCE_DOC_TOO_LARGE');
  }
  return Array.from(new Set(errors));
}

export async function createBox3Draft(
  request: Box3DraftRequest,
  options: { fetcher?: typeof fetch } = {},
): Promise<Box3DraftResponse> {
  const errors = validateBox3DraftRequest(request);
  if (errors.length) {
    throw new Box3DraftClientError(errors[0], 0, errors[0]);
  }

  const fetcher = options.fetcher ?? sidecarFetch;
  const response = await fetcher('/v1/cards/3/draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reference_docs: request.reference_docs,
      drafting_request: request.drafting_request,
      format_hint: request.format_hint,
      max_new_tokens: request.max_new_tokens ?? 512,
    }),
  } as RequestInit);

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    const failure = sanitizeFailure(payload);
    throw new Box3DraftClientError(failure.message, response.status, failure.failClass);
  }

  return payload as Box3DraftResponse;
}
