import { SIDECAR_BASE } from '../../constants';
import { assertLocalAdminPolicyUrl, isSha256Digest } from '../admin_policy/contracts';
import { getSidecarCapabilityToken } from '../connect_loop/sidecarAuth';
import {
  COMPANY_LEARNING_ENDPOINTS,
  type AdminContextForSidecar,
  type CompanyLearningConnectResponse,
  type CompanyLearningHandoffResponse,
  type CompanyLearningStatusResponse,
  type CompanyLearningUnderstanding,
  type SidecarErrorPayload,
} from './contracts';

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type TokenProvider = () => Promise<string>;

export type CompanyLearningRequestOptions = {
  fetcher?: Fetcher;
  tokenProvider?: TokenProvider;
  timeoutMs?: number;
  isProduction?: boolean;
};

export class CompanyLearningClientError extends Error {
  readonly status: number;
  readonly failClass: string;

  constructor(message: string, status: number, failClass = 'COMPANY_LEARNING_CLIENT_ERROR') {
    super(message);
    this.name = 'CompanyLearningClientError';
    this.status = status;
    this.failClass = failClass;
  }
}

function defaultIsProduction(): boolean {
  try {
    return Boolean((import.meta as unknown as { env?: { PROD?: boolean } }).env?.PROD);
  } catch {
    return false;
  }
}

const ZERO_DIGEST = `sha256:${'0'.repeat(64)}`;

function preValidateAdminContext(admin: AdminContextForSidecar, isProduction: boolean): void {
  if (admin.role !== 'admin') {
    throw new CompanyLearningClientError('관리자 권한이 필요합니다.', 0, 'ADMIN_RBAC_DENIED');
  }
  if (!isSha256Digest(admin.admin_id_digest) || !isSha256Digest(admin.admin_session_digest)) {
    throw new CompanyLearningClientError('관리자 인증 형식이 올바르지 않습니다.', 0, 'ADMIN_CONTEXT_INVALID');
  }
  if (admin.admin_id_digest === ZERO_DIGEST || admin.admin_session_digest === ZERO_DIGEST) {
    throw new CompanyLearningClientError('임시 관리자 식별값은 사용할 수 없습니다.', 0, 'ADMIN_DIGEST_PLACEHOLDER');
  }
  if (isProduction && admin.auth_method === 'test_only') {
    throw new CompanyLearningClientError('테스트 인증 방식은 운영 화면에서 사용할 수 없습니다.', 0, 'ADMIN_AUTH_METHOD_NOT_ALLOWED');
  }
}

function buildHeaders(token: string, admin: AdminContextForSidecar): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    'x-admin-role': admin.role,
    'x-admin-id-digest': admin.admin_id_digest,
    'x-admin-session-digest': admin.admin_session_digest,
    'x-admin-auth-method': admin.auth_method,
  };
}

function sanitizeBackendMessage(detail: unknown): SidecarErrorPayload {
  if (typeof detail === 'object' && detail !== null) {
    const record = detail as Record<string, unknown>;
    const fail_class = typeof record.fail_class === 'string' ? record.fail_class : 'BACKEND_VALIDATION_ERROR';
    const message = typeof record.message === 'string' ? record.message : fail_class;
    return { fail_class, message };
  }
  return { fail_class: 'BACKEND_ERROR', message: '회사 학습 후보 처리 오류' };
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
    admin: AdminContextForSidecar;
    options?: CompanyLearningRequestOptions;
  },
): Promise<T> {
  const options = init.options ?? {};
  preValidateAdminContext(init.admin, options.isProduction ?? defaultIsProduction());
  const url = `${SIDECAR_BASE}${path}`;
  assertLocalAdminPolicyUrl(url, path.split('?')[0]);

  const tokenProvider = options.tokenProvider ?? getSidecarCapabilityToken;
  let token: string;
  try {
    token = await tokenProvider();
  } catch {
    throw new CompanyLearningClientError('sidecar 통신 권한 토큰을 가져오지 못했습니다.', 0, 'SIDECAR_TOKEN_UNAVAILABLE');
  }

  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 30000;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const fetcher = options.fetcher ?? fetch;
  try {
    const response = await fetcher(url, {
      method: init.method,
      headers: buildHeaders(token, init.admin),
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });
    const payload = await readJsonOrError(response);
    if (!response.ok) {
      const detail = sanitizeBackendMessage((payload as { detail?: unknown }).detail ?? payload);
      throw new CompanyLearningClientError(detail.fail_class, response.status, detail.fail_class);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new CompanyLearningClientError('응답 시간 초과', 408, 'COMPANY_LEARNING_TIMEOUT');
    }
    if (error instanceof CompanyLearningClientError) {
      throw error;
    }
    throw new CompanyLearningClientError('로컬 sidecar 서버에 연결하지 못했습니다.', 0, 'SIDECAR_UNREACHABLE');
  } finally {
    clearTimeout(timeout);
  }
}

export function connectCompanyLearningFolder(
  folderPath: string,
  admin: AdminContextForSidecar,
  options: CompanyLearningRequestOptions = {},
): Promise<CompanyLearningConnectResponse> {
  return requestJson<CompanyLearningConnectResponse>(COMPANY_LEARNING_ENDPOINTS.connectFolder, {
    method: 'POST',
    body: { folder_path: folderPath },
    admin,
    options: { timeoutMs: 60000, ...options },
  });
}

export function getCompanyLearningStatus(
  jobId: string,
  admin: AdminContextForSidecar,
  options: CompanyLearningRequestOptions = {},
): Promise<CompanyLearningStatusResponse> {
  return requestJson<CompanyLearningStatusResponse>(COMPANY_LEARNING_ENDPOINTS.status(jobId), {
    method: 'GET',
    admin,
    options,
  });
}

export function getCompanyLearningUnderstanding(
  jobId: string,
  admin: AdminContextForSidecar,
  options: CompanyLearningRequestOptions = {},
): Promise<CompanyLearningUnderstanding> {
  return requestJson<CompanyLearningUnderstanding>(COMPANY_LEARNING_ENDPOINTS.understanding(jobId), {
    method: 'GET',
    admin,
    options,
  });
}

export function handoffCompanyLearningCandidate(
  jobId: string,
  adminConfirmedNeedsReview: boolean,
  admin: AdminContextForSidecar,
  options: CompanyLearningRequestOptions = {},
): Promise<CompanyLearningHandoffResponse> {
  return requestJson<CompanyLearningHandoffResponse>(COMPANY_LEARNING_ENDPOINTS.handoff, {
    method: 'POST',
    body: { job_id: jobId, admin_confirmed_needs_review: adminConfirmedNeedsReview },
    admin,
    options,
  });
}
