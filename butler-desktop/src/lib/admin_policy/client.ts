import {
  ADMIN_POLICY_ENDPOINTS,
  ADMIN_POLICY_SIDECAR_ORIGIN,
  assertLocalAdminPolicyUrl,
  type AdminHeaders,
  type CompanyFormatAdapterPreview,
  type CompanyFormatRegisterRequest,
  type CompanyFormatRegisterResponse,
  type CompanyPolicyRegisterRequest,
  type CompanyPolicyRegisterResponse,
  type PolicyGateEvaluateRequest,
  type PolicyGateResult,
  type Sha256Digest,
} from './contracts';

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class AdminPolicyClientError extends Error {
  readonly status: number;
  readonly failClass: string;

  constructor(message: string, status: number, failClass = 'ADMIN_POLICY_CLIENT_ERROR') {
    super(message);
    this.name = 'AdminPolicyClientError';
    this.status = status;
    this.failClass = failClass;
  }
}

export function buildAdminHeaderRecord(admin: AdminHeaders): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Admin-Role': admin.role,
    'X-Admin-Id-Digest': admin.admin_id_digest,
    'X-Admin-Session-Digest': admin.admin_session_digest,
    'X-Admin-Auth-Method': admin.auth_method,
  };
}

function sanitizeBackendMessage(detail: unknown): { failClass: string; message: string } {
  if (typeof detail === 'object' && detail !== null) {
    const record = detail as Record<string, unknown>;
    const failClass = typeof record.fail_class === 'string' ? record.fail_class : 'BACKEND_VALIDATION_ERROR';
    const message = typeof record.message === 'string' ? record.message : failClass;
    return { failClass, message };
  }
  if (typeof detail === 'string') {
    return { failClass: 'BACKEND_ERROR', message: detail.slice(0, 160) };
  }
  return { failClass: 'BACKEND_ERROR', message: 'Butler 관리자 정책 엔진 오류' };
}

async function readJsonOrError(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return { detail: response.statusText };
  }
}

async function requestJson<T>(
  path: string,
  init: {
    method: 'GET' | 'POST';
    body?: unknown;
    admin?: AdminHeaders;
    fetcher?: Fetcher;
    timeoutMs?: number;
  },
): Promise<T> {
  const url = `${ADMIN_POLICY_SIDECAR_ORIGIN}${path}`;
  assertLocalAdminPolicyUrl(url, path.split('?')[0]);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), init.timeoutMs ?? 30000);
  const fetcher = init.fetcher ?? fetch;
  try {
    const response = await fetcher(url, {
      method: init.method,
      headers: init.admin ? buildAdminHeaderRecord(init.admin) : { 'Content-Type': 'application/json' },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });
    const payload = await readJsonOrError(response);
    if (!response.ok) {
      const detail = sanitizeBackendMessage((payload as { detail?: unknown }).detail ?? payload);
      throw new AdminPolicyClientError(detail.message, response.status, detail.failClass);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new AdminPolicyClientError('응답 시간 초과 (30초)', 408, 'ADMIN_POLICY_TIMEOUT');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function registerCompanyPolicy(
  request: CompanyPolicyRegisterRequest,
  admin: AdminHeaders,
  options: { fetcher?: Fetcher; timeoutMs?: number } = {},
): Promise<CompanyPolicyRegisterResponse> {
  return requestJson<CompanyPolicyRegisterResponse>(ADMIN_POLICY_ENDPOINTS.registerPolicy, {
    method: 'POST',
    body: request,
    admin,
    ...options,
  });
}

export function registerCompanyFormat(
  request: CompanyFormatRegisterRequest,
  admin: AdminHeaders,
  options: { fetcher?: Fetcher; timeoutMs?: number } = {},
): Promise<CompanyFormatRegisterResponse> {
  return requestJson<CompanyFormatRegisterResponse>(ADMIN_POLICY_ENDPOINTS.registerFormat, {
    method: 'POST',
    body: request,
    admin,
    ...options,
  });
}

export function evaluateCompanyPolicy(
  request: PolicyGateEvaluateRequest,
  options: { fetcher?: Fetcher; timeoutMs?: number } = {},
): Promise<PolicyGateResult> {
  return requestJson<PolicyGateResult>(ADMIN_POLICY_ENDPOINTS.evaluatePolicy, {
    method: 'POST',
    body: request,
    ...options,
  });
}

export function getCompanyFormatAdapterPreview(
  formatId: string,
  draftDigest: Sha256Digest | null = null,
  options: { fetcher?: Fetcher; timeoutMs?: number } = {},
): Promise<CompanyFormatAdapterPreview> {
  const query = draftDigest ? `?draft_digest=${encodeURIComponent(draftDigest)}` : '';
  return requestJson<CompanyFormatAdapterPreview>(`${ADMIN_POLICY_ENDPOINTS.formatAdapterPreview(formatId)}${query}`, {
    method: 'GET',
    ...options,
  });
}
