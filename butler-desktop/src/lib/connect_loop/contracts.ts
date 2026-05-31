export const SIDECAR_ORIGIN = 'http://127.0.0.1:8765' as const;
export const ROUTER_DECIDE_URL = `${SIDECAR_ORIGIN}/v1/router/decide` as const;

export type Sha256Digest = `sha256:${string}`;
export type UserRole = 'employee' | 'manager' | 'admin';
export type IntentLabel =
  | 'memory_search'
  | 'form_convert'
  | 'draft_write'
  | 'accounting_classify'
  | 'general_chat'
  | 'unknown';
export type TargetBoxId = 'helper1' | '2' | '3' | '5' | 'chat' | 'none';
export type TargetEndpoint =
  | 'POST /v1/helpers/1/search'
  | 'POST /v1/cards/2/rewrite'
  | 'POST /v1/cards/3/draft'
  | 'POST /accounting/classify'
  | 'none';
export type PolicyPrecheck = 'allow' | 'needs_review' | 'block';

export interface ChatAttachmentDigest {
  content_digest: Sha256Digest;
  mime_type?: string;
  size_bytes?: number;
}

export interface ChatRequestV1 {
  request_id: string;
  session_id_digest: Sha256Digest;
  tenant_id_digest: Sha256Digest;
  device_id: string;
  user_role: UserRole;
  department_id_digest: Sha256Digest;
  text_ref: 'device_local_only';
  text_digest: Sha256Digest;
  attachments: ChatAttachmentDigest[];
  created_at: string;
  schema_version: 'chat_request.v1';
}

export interface RouterDecisionV1 {
  request_id: string;
  intent_label: IntentLabel;
  target_box_id: TargetBoxId;
  target_endpoint: TargetEndpoint;
  routing_confidence: number;
  reason_code: string;
  fallback_required: boolean;
  policy_precheck: PolicyPrecheck;
  schema_version: 'router_decision.v1';
}

export const ENDPOINT_ALLOWLIST = {
  'POST /v1/helpers/1/search': `${SIDECAR_ORIGIN}/v1/helpers/1/search`,
  'POST /v1/cards/2/rewrite': `${SIDECAR_ORIGIN}/v1/cards/2/rewrite`,
  'POST /v1/cards/3/draft': `${SIDECAR_ORIGIN}/v1/cards/3/draft`,
  'POST /accounting/classify': `${SIDECAR_ORIGIN}/accounting/classify`,
} as const satisfies Record<Exclude<TargetEndpoint, 'none'>, `${typeof SIDECAR_ORIGIN}${string}`>;

export const INTENT_BOX: Record<IntentLabel, TargetBoxId> = {
  memory_search: 'helper1',
  form_convert: '2',
  draft_write: '3',
  accounting_classify: '5',
  general_chat: 'chat',
  unknown: 'none',
};

export const INTENT_ENDPOINT: Record<Exclude<IntentLabel, 'general_chat' | 'unknown'>, Exclude<TargetEndpoint, 'none'>> = {
  memory_search: 'POST /v1/helpers/1/search',
  form_convert: 'POST /v1/cards/2/rewrite',
  draft_write: 'POST /v1/cards/3/draft',
  accounting_classify: 'POST /accounting/classify',
};

// 첨부 가드 (메인팀 v1.3): 개수 5개 + 총량 10MB 상한.
export const MAX_ATTACHMENTS = 5;
export const MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024;

const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const DATE_TIME_RE = /^\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\d|3[01])|(0[469]|11)-(0[1-9]|[12]\d|30)|02-(0[1-9]|[12]\d))T([01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d+)?(Z|[+-]([01]\d|2[0-3]):[0-5]\d)$/;
const REASON_RE = /^[A-Z][A-Z0-9_]{0,63}$/;

type DigestFn = (value: string) => Promise<Sha256Digest>;

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const expected = new Set(keys);
  return Object.keys(value).every(key => expected.has(key)) && keys.every(key => key in value);
}

function assert(condition: unknown, code: string): asserts condition {
  if (!condition) throw new Error(code);
}

export async function sha256TextDigest(value: string): Promise<Sha256Digest> {
  const subtle = globalThis.crypto?.subtle;
  assert(subtle, 'CRYPTO_SUBTLE_UNAVAILABLE');
  const bytes = new TextEncoder().encode(value);
  const buffer = await subtle.digest('SHA-256', bytes);
  const hex = Array.from(new Uint8Array(buffer))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('');
  return `sha256:${hex}`;
}

export function makeRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function createChatRequest(
  runtimeText: string,
  options: {
    hashText?: DigestFn;
    requestId?: string;
    now?: Date;
    userRole?: UserRole;
    attachments?: ChatAttachmentDigest[];
  } = {},
): Promise<ChatRequestV1> {
  const hashText = options.hashText ?? sha256TextDigest;
  const text_digest = await hashText(runtimeText);
  const request: ChatRequestV1 = {
    request_id: options.requestId ?? makeRequestId(),
    session_id_digest: await hashText('connect-loop-session'),
    tenant_id_digest: await hashText('connect-loop-tenant'),
    device_id: 'butler-desktop-device',
    user_role: options.userRole ?? 'employee',
    department_id_digest: await hashText('connect-loop-department'),
    text_ref: 'device_local_only',
    text_digest,
    attachments: options.attachments ?? [],
    created_at: (options.now ?? new Date()).toISOString(),
    schema_version: 'chat_request.v1',
  };
  assertValidChatRequest(request);
  return request;
}

export function assertValidChatRequest(value: unknown): asserts value is ChatRequestV1 {
  assert(typeof value === 'object' && value !== null && !Array.isArray(value), 'CHAT_REQUEST_NOT_OBJECT');
  const request = value as Record<string, unknown>;
  assert(
    exactKeys(request, [
      'request_id',
      'session_id_digest',
      'tenant_id_digest',
      'device_id',
      'user_role',
      'department_id_digest',
      'text_ref',
      'text_digest',
      'attachments',
      'created_at',
      'schema_version',
    ]),
    'CHAT_REQUEST_UNKNOWN_OR_MISSING_FIELD',
  );
  assert(typeof request.request_id === 'string' && request.request_id.length > 0, 'CHAT_REQUEST_ID_INVALID');
  for (const key of ['session_id_digest', 'tenant_id_digest', 'department_id_digest', 'text_digest'] as const) {
    assert(typeof request[key] === 'string' && DIGEST_RE.test(request[key]), `CHAT_REQUEST_${key.toUpperCase()}_INVALID`);
  }
  assert(typeof request.device_id === 'string' && request.device_id.length > 0, 'CHAT_REQUEST_DEVICE_ID_INVALID');
  assert(['employee', 'manager', 'admin'].includes(request.user_role as string), 'CHAT_REQUEST_USER_ROLE_INVALID');
  assert(request.text_ref === 'device_local_only', 'CHAT_REQUEST_TEXT_REF_INVALID');
  assert(Array.isArray(request.attachments), 'CHAT_REQUEST_ATTACHMENTS_INVALID');
  // 메인팀 v1.3: 개수 상한(5) + 총 바이트 상한(10MB). size_bytes 미기재는 0으로 계산.
  assert(request.attachments.length <= MAX_ATTACHMENTS, 'CHAT_ATTACHMENTS_TOO_MANY');
  let totalAttachmentBytes = 0;
  for (const attachment of request.attachments) {
    assert(typeof attachment === 'object' && attachment !== null && !Array.isArray(attachment), 'CHAT_ATTACHMENT_INVALID');
    const keys = Object.keys(attachment);
    assert(keys.every(key => ['content_digest', 'mime_type', 'size_bytes'].includes(key)), 'CHAT_ATTACHMENT_UNKNOWN_FIELD');
    const item = attachment as Record<string, unknown>;
    assert(typeof item.content_digest === 'string' && DIGEST_RE.test(item.content_digest), 'CHAT_ATTACHMENT_DIGEST_INVALID');
    if ('mime_type' in item) assert(typeof item.mime_type === 'string' && item.mime_type.length > 0, 'CHAT_ATTACHMENT_MIME_INVALID');
    if ('size_bytes' in item) assert(Number.isInteger(item.size_bytes) && Number(item.size_bytes) >= 0, 'CHAT_ATTACHMENT_SIZE_INVALID');
    totalAttachmentBytes += typeof item.size_bytes === 'number' ? item.size_bytes : 0;
  }
  assert(totalAttachmentBytes <= MAX_TOTAL_ATTACHMENT_BYTES, 'CHAT_ATTACHMENTS_TOTAL_TOO_LARGE');
  assert(typeof request.created_at === 'string' && DATE_TIME_RE.test(request.created_at), 'CHAT_REQUEST_CREATED_AT_INVALID');
  assert(request.schema_version === 'chat_request.v1', 'CHAT_REQUEST_SCHEMA_VERSION_INVALID');
}

export async function verifyChatRequestDigest(
  runtimeText: string,
  request: ChatRequestV1,
  hashText: DigestFn = sha256TextDigest,
): Promise<boolean> {
  return request.text_digest === await hashText(runtimeText);
}

export function assertValidRouterDecision(value: unknown): asserts value is RouterDecisionV1 {
  assert(typeof value === 'object' && value !== null && !Array.isArray(value), 'ROUTER_DECISION_NOT_OBJECT');
  const decision = value as Record<string, unknown>;
  assert(
    exactKeys(decision, [
      'request_id',
      'intent_label',
      'target_box_id',
      'target_endpoint',
      'routing_confidence',
      'reason_code',
      'fallback_required',
      'policy_precheck',
      'schema_version',
    ]),
    'ROUTER_DECISION_UNKNOWN_OR_MISSING_FIELD',
  );
  assert(typeof decision.request_id === 'string' && decision.request_id.length > 0, 'ROUTER_DECISION_REQUEST_ID_INVALID');
  assert(Object.keys(INTENT_BOX).includes(decision.intent_label as string), 'ROUTER_DECISION_INTENT_INVALID');
  assert(decision.target_box_id === INTENT_BOX[decision.intent_label as IntentLabel], 'ROUTER_DECISION_BOX_MISMATCH');
  assert(
    ['POST /v1/helpers/1/search', 'POST /v1/cards/2/rewrite', 'POST /v1/cards/3/draft', 'POST /accounting/classify', 'none'].includes(
      decision.target_endpoint as string,
    ),
    'ROUTER_DECISION_ENDPOINT_INVALID',
  );
  assert(typeof decision.routing_confidence === 'number' && decision.routing_confidence >= 0 && decision.routing_confidence <= 1, 'ROUTER_DECISION_CONFIDENCE_INVALID');
  assert(typeof decision.reason_code === 'string' && REASON_RE.test(decision.reason_code), 'ROUTER_DECISION_REASON_INVALID');
  assert(typeof decision.fallback_required === 'boolean', 'ROUTER_DECISION_FALLBACK_INVALID');
  assert(['allow', 'needs_review', 'block'].includes(decision.policy_precheck as string), 'ROUTER_DECISION_POLICY_INVALID');
  assert(decision.schema_version === 'router_decision.v1', 'ROUTER_DECISION_SCHEMA_VERSION_INVALID');

  if (decision.policy_precheck !== 'allow') {
    assert(decision.target_endpoint === 'none', 'ROUTER_DECISION_POLICY_ENDPOINT_NOT_CLOSED');
    assert(decision.fallback_required === true, 'ROUTER_DECISION_POLICY_FALLBACK_NOT_SET');
    return;
  }
  if (decision.intent_label === 'general_chat' || decision.intent_label === 'unknown') {
    assert(decision.target_endpoint === 'none', 'ROUTER_DECISION_FALLBACK_ENDPOINT_INVALID');
    assert(decision.fallback_required === true, 'ROUTER_DECISION_FALLBACK_NOT_SET');
    return;
  }
  assert(decision.target_endpoint === INTENT_ENDPOINT[decision.intent_label as keyof typeof INTENT_ENDPOINT], 'ROUTER_DECISION_ENDPOINT_MISMATCH');
}

export function assertLocalSidecarUrl(url: string): void {
  const parsed = new URL(url);
  const allowed = parsed.protocol === 'http:' && parsed.hostname === '127.0.0.1' && parsed.port === '8765';
  assert(allowed, 'BLOCK_NON_LOCAL_SIDECAR_URL');
}

export function resolveCallableEndpoint(decision: RouterDecisionV1): string | null {
  assertValidRouterDecision(decision);
  if (decision.policy_precheck !== 'allow') return null;
  if (decision.target_endpoint === 'none') return null;
  const url = (ENDPOINT_ALLOWLIST as Record<string, string>)[decision.target_endpoint];
  assert(url, 'BLOCK_UNREGISTERED_ENDPOINT');
  assertLocalSidecarUrl(url);
  return url;
}
