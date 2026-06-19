import { buildAdminHeadersInput, isSha256Digest, type AdminHeaders } from './contracts';
import type { AdminContextForSidecar } from '../company_fact/contracts';

/**
 * A-2 admin-context adapter.
 *
 * 이 파일은 신규 인증 체계가 아니다. 기존 admin-context 취득 방식
 * (`AdminPolicyConsole`/`CompanyFormatConsole`가 쓰는 `buildAdminHeadersInput`)의
 * 출력을 A-2 client가 요구하는 `AdminContextForSidecar` shape로 정렬하는 adapter다.
 *
 * 기존 코드베이스에는 zero-arg async provider / 전용 Tauri command / keychain flow가 없다
 * (Tauri command은 `get_sidecar_capability_token` 1개뿐 — docs/a2/repo_probe_evidence.md 참조).
 * admin-context는 콘솔 폼 입력 → `buildAdminHeadersInput` 검증 빌더로 생성된다. 그 방식을 그대로 재사용한다.
 */

/** 기존 AdminPolicyConsole 폼이 수집하는 입력 shape(동일 필드). */
export type ExistingAdminContextInput = {
  role: string;
  adminIdDigest: string;
  adminSessionDigest: string;
  authMethod: string;
};

const ZERO_DIGEST = `sha256:${'0'.repeat(64)}`;

export class AdminContextAdapterError extends Error {
  readonly failClass: string;

  constructor(message: string, failClass: string) {
    super(message);
    this.name = 'AdminContextAdapterError';
    this.failClass = failClass;
  }
}

/**
 * 기존 `AdminHeaders`를 A-2 `AdminContextForSidecar`로 정렬한다.
 * zero digest와 `test_only`는 여기서도 차단(backend가 최종 기준).
 */
export function normalizeAndValidateAdminContext(ctx: AdminHeaders): AdminContextForSidecar {
  if (ctx.role !== 'admin') {
    throw new AdminContextAdapterError('관리자 권한이 필요합니다.', 'ADMIN_RBAC_DENIED');
  }
  if (!isSha256Digest(ctx.admin_id_digest) || !isSha256Digest(ctx.admin_session_digest)) {
    throw new AdminContextAdapterError('관리자 인증 형식이 올바르지 않습니다.', 'ADMIN_CONTEXT_INVALID');
  }
  if (ctx.admin_id_digest === ZERO_DIGEST || ctx.admin_session_digest === ZERO_DIGEST) {
    throw new AdminContextAdapterError('임시 관리자 식별값은 사용할 수 없습니다. 실제 관리자 인증이 필요합니다.', 'ADMIN_DIGEST_PLACEHOLDER');
  }
  if (ctx.auth_method === 'test_only') {
    throw new AdminContextAdapterError('테스트 인증 방식은 운영 화면에서 사용할 수 없습니다.', 'ADMIN_AUTH_METHOD_NOT_ALLOWED');
  }
  return {
    role: 'admin',
    admin_id_digest: ctx.admin_id_digest,
    admin_session_digest: ctx.admin_session_digest,
    auth_method: ctx.auth_method,
  };
}

/**
 * 기존 provider(`buildAdminHeadersInput`)를 호출해 admin-context를 취득하고 A-2 shape로 정규화한다.
 * 입력은 기존 AdminPolicyConsole 폼과 동일하다. 새 provider/임시 digest를 만들지 않는다.
 */
export function getExistingAdminContextForA2(input: ExistingAdminContextInput): AdminContextForSidecar {
  let headers: AdminHeaders;
  try {
    headers = buildAdminHeadersInput(input);
  } catch (error) {
    const code = error instanceof Error ? error.message : '';
    if (code === 'ADMIN_ROLE_INVALID') {
      throw new AdminContextAdapterError('관리자 권한이 필요합니다.', 'ADMIN_RBAC_DENIED');
    }
    if (code === 'ADMIN_AUTH_METHOD_INVALID') {
      throw new AdminContextAdapterError('관리자 인증 방식이 올바르지 않습니다.', 'ADMIN_CONTEXT_INVALID');
    }
    // ADMIN_ID_DIGEST_INVALID / ADMIN_SESSION_DIGEST_INVALID 등 digest 형식 오류.
    throw new AdminContextAdapterError('관리자 인증 형식이 올바르지 않습니다.', 'ADMIN_CONTEXT_INVALID');
  }
  return normalizeAndValidateAdminContext(headers);
}
