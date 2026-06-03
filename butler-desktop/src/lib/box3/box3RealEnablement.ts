export type Box3RealStatus =
  | 'CONTRACT_ONLY'
  | 'ASSET_INVENTORY_PASS'
  | 'RUNNER_SMOKE_PASS'
  | 'REAL_CANDIDATE'
  | 'REAL_APPROVED'
  | 'BLOCKED';

export type Box3RealMetrics = {
  unsupported_claim_rate: number;
  no_evidence_claim_rate: number;
  citation_accuracy: number;
  format_compliance: number;
  style_compliance: number;
  table_figure_coverage: number;
  factual_claim_count: number;
  unsupported_count: number;
  no_evidence_count: number;
  supported_count: number;
};

export type Box3RealVerdictResponse = {
  schema_version: string;
  status: Box3RealStatus;
  request_id: string;
  request_digest: `sha256:${string}`;
  draft_text: string | null;
  draft_digest: `sha256:${string}` | null;
  metrics: Box3RealMetrics;
  fail_class: string | null;
  real_claim_allowed: boolean;
  human_approval_required: boolean;
  external_send_zero: true;
  raw_saved_zero: true;
  raw_text_logged: false;
  citations: Array<{ source_digest: `sha256:${string}`; evidence_digest: `sha256:${string}`; evidence_kind: string; span_label: 'runtime_only' }>;
  stage_trace: Array<Record<string, unknown>>;
};

const SIDECAR_ORIGIN = 'http://127.0.0.1:8765' as const;
const BOX3_ENDPOINT = `${SIDECAR_ORIGIN}/v1/cards/3/draft` as const;

export function assertBox3LocalUrl(url: string): void {
  const parsed = new URL(url);
  const ok = parsed.protocol === 'http:' && parsed.hostname === '127.0.0.1' && parsed.port === '8765' && parsed.pathname === '/v1/cards/3/draft';
  if (!ok) throw new Error('BLOCK_NON_LOCAL_BOX3_URL');
}

export async function requestBox3RealDraft(params: {
  token: string;
  referenceDocs: string[];
  draftingRequest: string;
  formatHint?: string;
  maxNewTokens?: number;
  docGrade?: 'restricted' | 'confidential' | 'internal' | 'public';
  timeoutMs?: number;
}): Promise<Box3RealVerdictResponse> {
  assertBox3LocalUrl(BOX3_ENDPOINT);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), params.timeoutMs ?? 30000);
  try {
    const response = await fetch(BOX3_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${params.token}`,
      },
      body: JSON.stringify({
        reference_docs: params.referenceDocs.map((content_runtime_text) => ({ content_runtime_text })),
        drafting_request: params.draftingRequest,
        format_hint: params.formatHint ?? 'freeform',
        max_new_tokens: params.maxNewTokens ?? 512,
        doc_grade: params.docGrade ?? 'internal',
      }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`BOX3_REAL_ENDPOINT_FAILED_${response.status}`);
    return await response.json() as Box3RealVerdictResponse;
  } finally {
    clearTimeout(timeout);
  }
}
