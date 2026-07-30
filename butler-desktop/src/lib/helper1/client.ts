import { sidecarFetch } from '../sidecarFetch';

export type Helper1WorkspaceState =
  | 'READY'
  | 'READY_TEST_ONLY'
  | 'ASSET_MISSING'
  | 'INDEXING'
  | 'VERIFYING'
  | 'INDEX_INVALID'
  | 'STALE'
  | 'FAILED';

export interface Helper1Status {
  schema_version: 'butler.helper1.status.v2';
  state: Helper1WorkspaceState;
  workspaces: Array<{ workspace_id: string; state: Helper1WorkspaceState }>;
  product_release_allowed: false;
  runtime_activation_allowed: false;
  production_claim_allowed: false;
  external_network_allowed: false;
}

export type Helper1AnswerKind =
  | 'ANSWERED'
  | 'REFUSED_NO_GROUNDING'
  | 'REFUSED_ASSET_MISSING'
  | 'REFUSED_POLICY'
  | 'REFUSED_DLP'
  | 'REFUSED_INJECTION'
  | 'REFUSED_INDEX_INVALID'
  | 'CANCELLED'
  | 'FAILED';

export interface Helper1Citation {
  claim_id: string;
  chunk_id: string;
  source_id: string;
  evidence_start: number;
  evidence_end: number;
  evidence_sha256: string;
}

export interface Helper1Answer {
  schema_version: 'butler.helper1.answer.v2';
  kind: Helper1AnswerKind;
  answer: string | null;
  request_id: string;
  workspace_id: string;
  generation_id: string | null;
  reason_code: string | null;
  model_identity_sha256: string | null;
  index_manifest_sha256: string | null;
  citations: Helper1Citation[];
  release_receipt_sha256: string | null;
}

export class Helper1ClientError extends Error {
  readonly status: number;
  readonly reasonCode: string;

  constructor(status: number, reasonCode: string) {
    super(reasonCode);
    this.name = 'Helper1ClientError';
    this.status = status;
    this.reasonCode = reasonCode;
  }
}

const WORKSPACE_STATES = new Set<Helper1WorkspaceState>([
  'READY',
  'READY_TEST_ONLY',
  'ASSET_MISSING',
  'INDEXING',
  'VERIFYING',
  'INDEX_INVALID',
  'STALE',
  'FAILED',
]);
const ANSWER_KINDS = new Set<Helper1AnswerKind>([
  'ANSWERED',
  'REFUSED_NO_GROUNDING',
  'REFUSED_ASSET_MISSING',
  'REFUSED_POLICY',
  'REFUSED_DLP',
  'REFUSED_INJECTION',
  'REFUSED_INDEX_INVALID',
  'CANCELLED',
  'FAILED',
]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_RE = /^[0-9a-f]{64}$/;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isNullableDigest(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && SHA256_RE.test(value));
}

function isWorkspaceState(value: unknown): value is Helper1WorkspaceState {
  return typeof value === 'string' && WORKSPACE_STATES.has(value as Helper1WorkspaceState);
}

function isAnswerKind(value: unknown): value is Helper1AnswerKind {
  return typeof value === 'string' && ANSWER_KINDS.has(value as Helper1AnswerKind);
}

function isCitation(value: unknown): value is Helper1Citation {
  if (!isObject(value)) return false;
  return (
    typeof value.claim_id === 'string'
    && typeof value.chunk_id === 'string'
    && typeof value.source_id === 'string'
    && Number.isSafeInteger(value.evidence_start)
    && Number.isSafeInteger(value.evidence_end)
    && (value.evidence_start as number) >= 0
    && (value.evidence_end as number) > (value.evidence_start as number)
    && typeof value.evidence_sha256 === 'string'
    && SHA256_RE.test(value.evidence_sha256)
  );
}

async function readObject(response: Response): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await response.json();
    if (isObject(value)) return value;
  } catch {
    // Emit only the stable code below; raw sidecar output is never surfaced.
  }
  throw new Helper1ClientError(response.status, 'HELPER1_RESPONSE_INVALID');
}

function parseStatus(value: Record<string, unknown>, status: number): Helper1Status {
  const workspaces = value.workspaces;
  if (
    value.schema_version !== 'butler.helper1.status.v2'
    || !isWorkspaceState(value.state)
    || !Array.isArray(workspaces)
    || !workspaces.every(workspace => (
      isObject(workspace)
      && typeof workspace.workspace_id === 'string'
      && UUID_RE.test(workspace.workspace_id)
      && isWorkspaceState(workspace.state)
    ))
    || value.product_release_allowed !== false
    || value.runtime_activation_allowed !== false
    || value.production_claim_allowed !== false
    || value.external_network_allowed !== false
  ) {
    throw new Helper1ClientError(status, 'HELPER1_STATUS_INVALID');
  }
  return value as unknown as Helper1Status;
}

function parseAnswer(value: Record<string, unknown>, status: number): Helper1Answer {
  const citations = value.citations;
  const answered = value.kind === 'ANSWERED';
  if (
    value.schema_version !== 'butler.helper1.answer.v2'
    || !isAnswerKind(value.kind)
    || typeof value.request_id !== 'string'
    || !UUID_RE.test(value.request_id)
    || typeof value.workspace_id !== 'string'
    || !UUID_RE.test(value.workspace_id)
    || !isNullableString(value.generation_id)
    || !isNullableString(value.reason_code)
    || !isNullableDigest(value.model_identity_sha256)
    || !isNullableDigest(value.index_manifest_sha256)
    || !isNullableDigest(value.release_receipt_sha256)
    || !Array.isArray(citations)
    || !citations.every(isCitation)
    || (answered && (typeof value.answer !== 'string' || value.answer.length === 0))
    || (!answered && value.answer !== null)
    || (answered && value.reason_code !== null)
    || (!answered && (typeof value.reason_code !== 'string' || value.reason_code.length === 0))
  ) {
    throw new Helper1ClientError(status, 'HELPER1_ANSWER_INVALID');
  }
  return value as unknown as Helper1Answer;
}

export async function fetchHelper1Status(): Promise<Helper1Status> {
  const response = await sidecarFetch('/v1/helpers/1/status');
  const value = await readObject(response);
  if (!response.ok) throw new Helper1ClientError(response.status, 'HELPER1_STATUS_UNAVAILABLE');
  return parseStatus(value, response.status);
}

export async function askHelper1(
  workspaceId: string,
  query: string,
  signal?: AbortSignal,
): Promise<Helper1Answer> {
  if (!UUID_RE.test(workspaceId) || query.length === 0 || query.length > 4000) {
    throw new Helper1ClientError(0, 'HELPER1_REQUEST_INVALID');
  }
  const response = await sidecarFetch('/v1/helpers/1/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      schema_version: 'butler.helper1.ask-request.v2',
      request_id: crypto.randomUUID(),
      workspace_id: workspaceId,
      query,
      top_k: 5,
      requested_generation_id: null,
      effect_intent: 'display_only',
    }),
    signal,
  });
  return parseAnswer(await readObject(response), response.status);
}
