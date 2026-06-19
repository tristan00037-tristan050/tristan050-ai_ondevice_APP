import { SIDECAR_BASE } from '../../constants';
import { getSidecarCapabilityToken } from '../connect_loop/sidecarAuth';
import { assertLocalAdminPolicyUrl, isSha256Digest } from '../admin_policy/contracts';
import {
  COMPANY_FACT_ENDPOINTS,
  type AdminContextForSidecar,
  type CompanyFactApproveResponse,
  type CompanyFactCandidateDetail,
  type CompanyFactCandidatesResponse,
  type CompanyFactDeprecateResponse,
  type CompanyFactsStatusResponse,
  type SidecarErrorPayload,
} from './contracts';

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type TokenProvider = () => Promise<string>;

/** 운영 build 판정(테스트 인증 차단 기준). 테스트에서 options로 override 가능. */
function defaultIsProduction(): boolean {
  try {
    return Boolean((import.meta as unknown as { env?: { PROD?: boolean } }).env?.PROD);
  } catch {
    return false;
  }
}

export type CompanyFactRequestOptions = {
  fetcher?: Fetcher;
  tokenProvider?: TokenProvider;
  timeoutMs?: number;
  isProduction?: boolean;
};

export class CompanyFactClientError extends Error {
  readonly status: number;
  readonly failClass: string;

  constructor(message: string, status: number, failClass = 'COMPANY_FACT_CLIENT_ERROR') {
    super(message);
    this.name = 'CompanyFactClientError';
    this.status = status;
    this.failClass = failClass;
  }
}

/** sha256:0{64} placeholder digest(차단 대상). 리터럴을 소스에 남기지 않도록 조합으로 생성. */
const ZERO_DIGEST = `sha256:${'0'.repeat(64)}`;

/**
 * admin route 호출 전 frontend 선검증. backend가 최종 권한 기준이지만, 명백한 placeholder/test 인증은
 * request 전에 fail_class로 차단해 불필요한 호출과 UX 혼동을 막는다.
 */
function preValidateAdminContext(admin: AdminContextForSidecar, isProduction: boolean): void {
  if (admin.role !== 'admin') {
    throw new CompanyFactClientError('관리자 권한이 필요합니다.', 0, 'ADMIN_RBAC_DENIED');
  }
  if (!isSha256Digest(admin.admin_id_digest) || !isSha256Digest(admin.admin_session_digest)) {
    throw new CompanyFactClientError('관리자 인증 형식이 올바르지 않습니다.', 0, 'ADMIN_CONTEXT_INVALID');
  }
  if (admin.admin_id_digest === ZERO_DIGEST || admin.admin_session_digest === ZERO_DIGEST) {
    throw new CompanyFactClientError('임시 관리자 식별값은 사용할 수 없습니다.', 0, 'ADMIN_DIGEST_PLACEHOLDER');
  }
  if (isProduction && admin.auth_method === 'test_only') {
    throw new CompanyFactClientError('테스트 인증 방식은 운영 화면에서 사용할 수 없습니다.', 0, 'ADMIN_AUTH_METHOD_NOT_ALLOWED');
  }
}

function buildHeaders(token: string, admin?: AdminContextForSidecar): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    // 기존 sidecar client 관례: 모든 요청에 capability token을 Bearer로 부착.
    Authorization: `Bearer ${token}`,
  };
  if (admin) {
    headers['x-admin-role'] = admin.role;
    headers['x-admin-id-digest'] = admin.admin_id_digest;
    headers['x-admin-session-digest'] = admin.admin_session_digest;
    headers['x-admin-auth-method'] = admin.auth_method;
  }
  return headers;
}

function sanitizeBackendMessage(detail: unknown): SidecarErrorPayload {
  if (typeof detail === 'object' && detail !== null) {
    const record = detail as Record<string, unknown>;
    const fail_class = typeof record.fail_class === 'string' ? record.fail_class : 'BACKEND_VALIDATION_ERROR';
    const message = typeof record.message === 'string' ? record.message : fail_class;
    return { fail_class, message };
  }
  if (typeof detail === 'string') {
    return { fail_class: 'BACKEND_ERROR', message: detail.slice(0, 160) };
  }
  return { fail_class: 'BACKEND_ERROR', message: 'Butler 회사 지식 엔진 오류' };
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
    admin?: AdminContextForSidecar;
    options?: CompanyFactRequestOptions;
  },
): Promise<T> {
  const options = init.options ?? {};
  if (init.admin) {
    preValidateAdminContext(init.admin, options.isProduction ?? defaultIsProduction());
  }

  const url = `${SIDECAR_BASE}${path}`;
  assertLocalAdminPolicyUrl(url, path.split('?')[0]);

  const tokenProvider = options.tokenProvider ?? getSidecarCapabilityToken;
  let token: string;
  try {
    token = await tokenProvider();
  } catch {
    throw new CompanyFactClientError('sidecar 통신 권한 토큰을 가져오지 못했습니다. 앱을 재시작해 주세요.', 0, 'SIDECAR_TOKEN_UNAVAILABLE');
  }

  const fetcher = options.fetcher ?? fetch;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30000);
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
      throw new CompanyFactClientError(detail.message, response.status, detail.fail_class);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new CompanyFactClientError('응답 시간 초과 (30초)', 408, 'COMPANY_FACT_TIMEOUT');
    }
    if (error instanceof CompanyFactClientError) {
      throw error;
    }
    // fetch 자체 실패(네트워크/Load failed) — raw 미로깅, method/path만 보존.
    throw new CompanyFactClientError('로컬 sidecar 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.', 0, 'SIDECAR_UNREACHABLE');
  } finally {
    clearTimeout(timeout);
  }
}

// ── 7 endpoints ─────────────────────────────────────────────────────────────

/** #2 후보 목록 — admin headers. */
export function listCompanyFactCandidates(
  admin: AdminContextForSidecar,
  options: CompanyFactRequestOptions = {},
): Promise<CompanyFactCandidatesResponse> {
  return requestJson<CompanyFactCandidatesResponse>(COMPANY_FACT_ENDPOINTS.listCandidates, {
    method: 'GET',
    admin,
    options,
  });
}

/** #3 후보 상세 — admin headers. answer_runtime_text 포함. */
export function getCompanyFactCandidate(
  factId: string,
  admin: AdminContextForSidecar,
  options: CompanyFactRequestOptions = {},
): Promise<CompanyFactCandidateDetail> {
  return requestJson<CompanyFactCandidateDetail>(COMPANY_FACT_ENDPOINTS.candidateDetail(factId), {
    method: 'GET',
    admin,
    options,
  });
}

/** #4 후보 승인 — capability token + admin headers. CANDIDATE -> ACTIVE. */
export function approveCompanyFactCandidate(
  factId: string,
  admin: AdminContextForSidecar,
  options: CompanyFactRequestOptions = {},
): Promise<CompanyFactApproveResponse> {
  return requestJson<CompanyFactApproveResponse>(COMPANY_FACT_ENDPOINTS.approveCandidate(factId), {
    method: 'POST',
    admin,
    options,
  });
}

/** #5 후보/지식 폐기 — capability token + admin headers. -> DEPRECATED. */
export function deprecateCompanyFact(
  factId: string,
  admin: AdminContextForSidecar,
  options: CompanyFactRequestOptions = {},
): Promise<CompanyFactDeprecateResponse> {
  return requestJson<CompanyFactDeprecateResponse>(COMPANY_FACT_ENDPOINTS.deprecateFact(factId), {
    method: 'POST',
    admin,
    options,
  });
}

/** #6 상태 — capability token. active_count/candidate_count. */
export function getCompanyFactsStatus(options: CompanyFactRequestOptions = {}): Promise<CompanyFactsStatusResponse> {
  return requestJson<CompanyFactsStatusResponse>(COMPANY_FACT_ENDPOINTS.status, {
    method: 'GET',
    options,
  });
}

/** #1 후보 제출 — capability token. 입력/테스트 fixture용(승인 콘솔 핵심 아님). */
export function submitCompanyFactCandidate(
  candidate: Record<string, unknown>,
  options: CompanyFactRequestOptions = {},
): Promise<{ fact_id: string; status: string }> {
  return requestJson<{ fact_id: string; status: string }>(COMPANY_FACT_ENDPOINTS.submitCandidate, {
    method: 'POST',
    body: candidate,
    options,
  });
}
