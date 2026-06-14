export const ADMIN_POLICY_SIDECAR_ORIGIN = 'http://127.0.0.1:8765' as const;

export const ADMIN_POLICY_ENDPOINTS = {
  registerPolicy: '/v1/admin/company-policy',
  registerFormat: '/v1/admin/company-format',
  evaluatePolicy: '/v1/policy/evaluate',
  formatAdapterPreview: (formatId: string) => `/v1/admin/company-format/${encodeURIComponent(formatId)}/adapter`,
} as const;

export type Sha256Digest = `sha256:${string}`;
export type AdminRole = 'admin' | 'manager' | 'employee';
export type AdminAuthMethod = 'os_keychain' | 'tauri_secure_invoke' | 'test_only';
export type CompanyPolicyStatus = 'DRAFT' | 'ACTIVE' | 'DEPRECATED';
export type DocGrade = 'restricted' | 'confidential' | 'internal' | 'public';
export type PolicyDecision = 'allow' | 'needs_review' | 'block';
export type FormatKind =
  | 'report'
  | 'proposal'
  | 'official_letter'
  | 'summary'
  | 'contract_review'
  | 'meeting_agenda'
  | 'freeform'
  | 'cash_flow_daily'
  | 'cash_flow_weekly'
  | 'cash_flow_monthly'
  | 'voucher'
  | 'financial_statement'
  | 'pnl_summary';

export const DOC_GRADES: readonly DocGrade[] = ['restricted', 'confidential', 'internal', 'public'];
export const POLICY_DECISIONS: readonly PolicyDecision[] = ['allow', 'needs_review', 'block'];
export const ADMIN_ROLES: readonly AdminRole[] = ['admin', 'manager', 'employee'];
export const POLICY_STATUSES: readonly CompanyPolicyStatus[] = ['DRAFT', 'ACTIVE', 'DEPRECATED'];
export const FORMAT_KINDS: readonly FormatKind[] = [
  'report',
  'proposal',
  'official_letter',
  'summary',
  'contract_review',
  'meeting_agenda',
  'freeform',
  'cash_flow_daily',
  'cash_flow_weekly',
  'cash_flow_monthly',
  'voucher',
  'financial_statement',
  'pnl_summary',
];

export const FORMAT_KIND_LABELS: Record<FormatKind, string> = {
  report: '보고서',
  proposal: '제안서',
  official_letter: '공문',
  summary: '요약',
  contract_review: '계약 검토',
  meeting_agenda: '회의 안건',
  freeform: '자유형',
  cash_flow_daily: '일간 현금흐름',
  cash_flow_weekly: '주간 현금흐름',
  cash_flow_monthly: '월간 현금흐름',
  voucher: '전표',
  financial_statement: '재무제표',
  pnl_summary: '손익 요약',
};

export const DOC_GRADE_LABELS: Record<DocGrade, string> = {
  restricted: '기밀',
  confidential: '대외비',
  internal: '내부',
  public: '공개',
};

export const POLICY_DECISION_LABELS: Record<PolicyDecision, string> = {
  allow: '허용',
  needs_review: '검토 필요',
  block: '차단',
};

export const DEFAULT_EXTERNAL_SEND_RULES: Readonly<Record<DocGrade, PolicyDecision>> = {
  restricted: 'block',
  confidential: 'block',
  internal: 'needs_review',
  public: 'allow',
};

export type AdminHeaders = {
  role: AdminRole;
  admin_id_digest: Sha256Digest;
  admin_session_digest: Sha256Digest;
  auth_method: AdminAuthMethod;
};

export type AccessRulePayload = {
  dept_digest: Sha256Digest;
  role: AdminRole;
  doc_grade: DocGrade;
  decision: PolicyDecision;
  reason_code: string;
};

export type CompanyPolicyRegisterRequest = {
  version: number;
  status: CompanyPolicyStatus;
  access_rules: AccessRulePayload[];
  masking_engine_verified: boolean;
};

export type CompanyPolicyRegisterResponse = {
  schema_version: 'admin.company_policy_register.response.v1';
  policy_digest: Sha256Digest;
  audit_ref: Sha256Digest;
  admin_rbac_verified: true;
  raw_saved_zero: true;
  raw_text_logged: false;
};

export type CompanyFormatRegisterRequest = {
  template_runtime_text: string;
  format_kind: FormatKind;
  title_runtime_text: string;
  language: string;
  dept_digest: Sha256Digest;
};

export type CompanyFormatRegisterResponse = {
  schema_version: 'admin.company_format_register.response.v1';
  format_id: string;
  format_digest: Sha256Digest;
  template_digest: Sha256Digest;
  template_ref: string;
  audit_ref: Sha256Digest;
  encrypted_store: true;
  raw_saved_zero: true;
  raw_text_logged: false;
};

export type PolicyGateEvaluateRequest = {
  request_id: string;
  tenant_digest: Sha256Digest;
  dept_digest: Sha256Digest;
  user_role: AdminRole;
  target_box_id: string;
  operation: string;
  doc_grade: DocGrade;
  external_send_requested: boolean;
  format_id: string | null;
  learning_allowed: boolean;
  retention_days: number;
  masking_requested: boolean;
};

export type PolicyGateResult = {
  schema_version: 'policy_gate_result.v1';
  allowed: boolean;
  decision: PolicyDecision;
  block_reason: string | null;
  applied_policy_digest: Sha256Digest | null;
  audit_ref: Sha256Digest;
  external_send_zero: true;
  raw_text_logged: false;
};

export type CompanyFormatAdapterPreview = {
  schema_version: 'helper3.company_format_adapter.v1';
  format_id: string;
  registered: boolean;
  active: boolean;
  format_digest: Sha256Digest | null;
  template_digest: Sha256Digest | null;
  needs_review: boolean;
  reason_code: string | null;
  draft_digest_echo: Sha256Digest | null;
};

export function isSha256Digest(value: string): value is Sha256Digest {
  return /^sha256:[0-9a-f]{64}$/.test(value);
}

export function requireSha256Digest(value: string, fieldName: string): Sha256Digest {
  if (!isSha256Digest(value)) {
    throw new Error(`${fieldName}_DIGEST_INVALID`);
  }
  return value;
}

export function isReasonCode(value: string): boolean {
  return /^[A-Z][A-Z0-9_]{0,63}$/.test(value);
}

export function assertLocalAdminPolicyUrl(url: string, expectedPath?: string): void {
  const parsed = new URL(url);
  const allowed =
    parsed.protocol === 'http:' &&
    parsed.hostname === '127.0.0.1' &&
    parsed.port === '8765' &&
    (expectedPath ? parsed.pathname === expectedPath : parsed.origin === ADMIN_POLICY_SIDECAR_ORIGIN);
  if (!allowed) {
    throw new Error('BLOCK_NON_LOCAL_ADMIN_POLICY_URL');
  }
}

export function buildAdminHeadersInput(input: {
  role: string;
  adminIdDigest: string;
  adminSessionDigest: string;
  authMethod: string;
}): AdminHeaders {
  if (!ADMIN_ROLES.includes(input.role as AdminRole)) {
    throw new Error('ADMIN_ROLE_INVALID');
  }
  if (!['os_keychain', 'tauri_secure_invoke', 'test_only'].includes(input.authMethod)) {
    throw new Error('ADMIN_AUTH_METHOD_INVALID');
  }
  return {
    role: input.role as AdminRole,
    admin_id_digest: requireSha256Digest(input.adminIdDigest, 'ADMIN_ID'),
    admin_session_digest: requireSha256Digest(input.adminSessionDigest, 'ADMIN_SESSION'),
    auth_method: input.authMethod as AdminAuthMethod,
  };
}

export function validateAccessRule(rule: AccessRulePayload): string[] {
  const errors: string[] = [];
  if (!isSha256Digest(rule.dept_digest)) errors.push('DEPT_DIGEST_INVALID');
  if (!ADMIN_ROLES.includes(rule.role)) errors.push('ACCESS_RULE_ROLE_INVALID');
  if (!DOC_GRADES.includes(rule.doc_grade)) errors.push('ACCESS_RULE_DOC_GRADE_INVALID');
  if (!POLICY_DECISIONS.includes(rule.decision)) errors.push('ACCESS_RULE_DECISION_INVALID');
  if (!isReasonCode(rule.reason_code)) errors.push('ACCESS_RULE_REASON_CODE_INVALID');
  return errors;
}

export function validateCompanyPolicyRegisterRequest(request: CompanyPolicyRegisterRequest): string[] {
  const errors: string[] = [];
  if (!Number.isInteger(request.version) || request.version < 1) {
    errors.push('POLICY_VERSION_INVALID');
  }
  if (!POLICY_STATUSES.includes(request.status)) {
    errors.push('POLICY_STATUS_INVALID');
  }
  if (!Array.isArray(request.access_rules) || request.access_rules.length === 0) {
    errors.push('ACCESS_RULES_REQUIRED');
  }
  for (const rule of request.access_rules) {
    errors.push(...validateAccessRule(rule));
  }
  if (typeof request.masking_engine_verified !== 'boolean') {
    errors.push('MASKING_ENGINE_VERIFIED_INVALID');
  }
  return [...new Set(errors)];
}

export function validateCompanyFormatRegisterRequest(request: CompanyFormatRegisterRequest): string[] {
  const errors: string[] = [];
  if (!request.template_runtime_text.trim()) errors.push('TEMPLATE_RUNTIME_TEXT_REQUIRED');
  if (request.template_runtime_text.length > 200000) errors.push('TEMPLATE_RUNTIME_TEXT_TOO_LONG');
  if (!request.title_runtime_text.trim()) errors.push('TITLE_RUNTIME_TEXT_REQUIRED');
  if (request.title_runtime_text.length > 1000) errors.push('TITLE_RUNTIME_TEXT_TOO_LONG');
  if (!FORMAT_KINDS.includes(request.format_kind)) errors.push('FORMAT_KIND_INVALID');
  if (!request.language.trim()) errors.push('LANGUAGE_REQUIRED');
  if (!isSha256Digest(request.dept_digest)) errors.push('DEPT_DIGEST_INVALID');
  return errors;
}
