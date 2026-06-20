import type { AdminAuthMethod, Sha256Digest } from '../admin_policy/contracts';

/**
 * A-2 회사 지식 후보 승인 콘솔 contracts.
 *
 * raw-0 불변식:
 *  - `answer_runtime_text`(후보 원문)는 상세(`CompanyFactCandidateDetail`)에만 둔다.
 *  - 목록 row(`CompanyFactCandidateIndexEntry`)에는 원문 preview를 저장하지 않는다.
 *    필요 시 상세 호출 후 화면 메모리(React state)에만 보관한다.
 *  - 응답 flag `raw_text_logged=false`, `external_send_zero=true`를 검증 가능한 필드로 둔다.
 */

export const COMPANY_FACT_SIDECAR_ORIGIN = 'http://127.0.0.1:8765' as const;

export const COMPANY_FACT_ENDPOINTS = {
  /** POST — capability token. 후보 제출(입력/테스트 fixture). */
  submitCandidate: '/v1/company-facts/candidates',
  /** GET — admin headers. 승인 콘솔 목록. */
  listCandidates: '/v1/company-facts/candidates',
  /** GET — admin headers. 상세(answer_runtime_text 포함). */
  candidateDetail: (factId: string) => `/v1/company-facts/candidates/${encodeURIComponent(factId)}`,
  /** POST — capability token + admin headers. CANDIDATE -> ACTIVE. */
  approveCandidate: (factId: string) => `/v1/company-facts/candidates/${encodeURIComponent(factId)}/approve`,
  /** POST — capability token + admin headers. CANDIDATE/ACTIVE -> DEPRECATED. */
  deprecateFact: (factId: string) => `/v1/company-facts/${encodeURIComponent(factId)}/deprecate`,
  /** POST — capability token + admin headers. ACTIVE -> DEPRECATED + replacement ACTIVE. */
  supersedeFact: (factId: string) => `/v1/company-facts/${encodeURIComponent(factId)}/supersede`,
  /** POST — capability token + admin headers. known-bad warning override for one candidate digest. */
  overrideKnownBad: (factId: string) =>
    `/v1/company-facts/candidates/${encodeURIComponent(factId)}/known-bad/override`,
  /** GET — capability token. active_count/candidate_count. */
  status: '/v1/company-facts/status',
} as const;

export type CompanyFactStatus = 'CANDIDATE' | 'ACTIVE' | 'DEPRECATED';
export type DeprecateReasonCode = 'WRONG' | 'SUPERSEDED' | 'MANUAL_DEPRECATED';

/**
 * A-2 client가 요구하는 admin-context shape.
 * 기존 `AdminHeaders`(admin_policy/contracts.ts)를 adapter(`adminContext.ts`)에서 이 shape로 정렬한다.
 * 승인/폐기 권한은 항상 role='admin'.
 */
export type AdminContextForSidecar = {
  role: 'admin';
  admin_id_digest: Sha256Digest;
  admin_session_digest: Sha256Digest;
  auth_method: AdminAuthMethod;
};

/** raw-0: 응답이 검증 가능하도록 노출하는 flag(선택적, backend가 포함하면 false/true여야 함). */
export type RawZeroFlags = {
  raw_text_logged?: false;
  external_send_zero?: true;
};

export type KnownBadWarning = RawZeroFlags & {
  known_bad_suspected: boolean;
  override_available: boolean;
  override_active: boolean;
  match_score: number | null;
  matched_keywords_count: number;
  matched_pattern_digest: string | null;
  bad_entry_id: string | null;
  bad_fact_digest: string | null;
};

/** 목록 row — 원문 preview 없음(raw-0). */
export type CompanyFactCandidateIndexEntry = {
  fact_id: string;
  status: CompanyFactStatus;
  category: string;
  question_patterns: string[];
  keywords_required: string[];
  keywords_any: string[];
  source: string | null;
  source_url: string | null;
  source_doc: string | null;
  verified_at: string | null;
  expires_at: string | null;
  confidence: number | null;
  fact_digest?: string;
  known_bad?: KnownBadWarning;
};

/** 상세 — answer_runtime_text는 여기에만 존재. */
export type CompanyFactCandidateDetail = CompanyFactCandidateIndexEntry &
  RawZeroFlags & {
    answer_runtime_text: string;
    fact_digest: string;
  };

export type CompanyFactCandidatesResponse = RawZeroFlags & {
  candidates: CompanyFactCandidateIndexEntry[];
  active_count?: number;
  candidate_count?: number;
};

export type CompanyFactApproveResponse = RawZeroFlags & {
  fact_id: string;
  status: CompanyFactStatus;
};

export type CompanyFactDeprecateResponse = RawZeroFlags & {
  fact_id: string;
  status: CompanyFactStatus;
  fact_digest?: string;
  audit_ref?: string;
};

export type CompanyFactSupersedeRequest = {
  category: string;
  question_patterns: string[];
  keywords_required: string[];
  keywords_any: string[];
  answer_runtime_text: string;
  source: string;
  source_url?: string | null;
  source_doc?: string | null;
  verified_at?: string | null;
  expires_at?: string | null;
  confidence: 1.0;
};

export type CompanyFactSupersedeResponse = RawZeroFlags & {
  schema_version: 'company_fact.supersede.result.v1';
  old_fact_id: string;
  old_status: CompanyFactStatus;
  old_fact_digest: string;
  new_fact_id: string;
  new_status: CompanyFactStatus;
  new_fact_digest: string;
  previous_fact_digest: string;
  audit_refs: string[];
};

export type CompanyFactKnownBadOverrideResponse = RawZeroFlags & {
  schema_version: 'company_fact.known_bad_override.v1';
  fact_id: string;
  candidate_fact_digest: string;
  bad_entry_id: string;
  bad_fact_digest: string;
  approved_by_digest: string;
  approved_at: string;
  status: 'ACTIVE';
  override_digest: string;
  audit_ref: string;
};

export type CompanyFactsStatusResponse = RawZeroFlags & {
  active_count: number;
  candidate_count: number;
};

/** backend 오류 표준 페이로드(allowlist 렌더링용 — fail_class와 안전 메시지만). */
export type SidecarErrorPayload = {
  fail_class: string;
  message: string;
};

/** 화면에 렌더링 허용되는 후보 필드(raw-0 allowlist). digest/token/path는 절대 포함하지 않는다. */
export const COMPANY_FACT_DISPLAY_FIELDS = [
  'fact_id',
  'status',
  'category',
  'question_patterns',
  'keywords_required',
  'keywords_any',
  'answer_runtime_text',
  'source',
  'source_url',
  'source_doc',
  'verified_at',
  'expires_at',
  'confidence',
  'known_bad',
] as const;
