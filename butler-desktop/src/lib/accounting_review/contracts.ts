export type CapabilityState =
  | 'NOT_REGISTERED'
  | 'REGISTERED_NOT_CONSUMED'
  | 'PARTIALLY_CONSUMED'
  | 'CONSUMED'
  | 'DEGRADED'
  | 'UNAVAILABLE';

export interface AccountingReviewCapabilityStatus {
  schema_version: 'butler.accounting_capability_status.v2';
  capability_id: 'accounting.user_assignment';
  status: CapabilityState;
  registered: boolean;
  required_routes: number;
  covered_routes: number;
  self_test: 'PASS' | 'FAIL' | 'NOT_RUN';
  reason_codes: string[];
  verified_at: string;
  registry_digest: string;
  overlay_digest: string;
  event_count: number;
  evidence_digest: string;
}

export interface ReviewSummary {
  schema_version: '3.0';
  batch_id: string;
  batch_version: number;
  registry_digest: string;
  overlay_digest: string;
  counts: {
    source_declared_valid: number;
    auto_propose: number;
    user_rule_applied_draft: number;
    review_required: number;
    review_quarantine: number;
    non_expense_bank_event: number;
    user_assigned: number;
  };
  total_input_rows: number;
  generated_at: string;
  evidence_digest: string;
}

export type ReviewState = 'AUTO_PROPOSE' | 'USER_RULE_APPLIED_DRAFT' | 'REVIEW_REQUIRED';

export interface ReviewItem {
  txn_id: string;
  transaction_version: number;
  booked_date: string;
  money: { currency: string; minor_units: number };
  descriptor_display: string;
  display_policy: 'PLAIN' | 'MASKED' | 'RESTRICTED';
  bank_direction: 'INFLOW' | 'OUTFLOW';
  review_state: ReviewState;
  suggestion: null | {
    account_id: string;
    source: 'AUTO_PROPOSE' | 'USER_RULE_APPLIED_DRAFT';
    safe_reason: string;
    rule_id?: string | null;
  };
}

export interface UnaccountedPage {
  schema_version: '3.0';
  batch_id: string;
  batch_version: number;
  registry_digest: string;
  overlay_digest: string;
  items: ReviewItem[];
  total_count: number;
  next_cursor: string | null;
  etag: string;
}

export interface QuarantinedRow {
  row_id: string;
  batch_id: string;
  source_row_number: number;
  source_row_fingerprint: string;
  reason_code: 'INVALID_AMOUNT' | 'ZERO_AMOUNT_REVIEW' | 'INVALID_BOOKING_DATE';
  state: 'QUARANTINED';
  resource_version: number;
}

export interface ChartEntry {
  account_id: string;
  account_code: string | null;
  display_name: string;
  category_path: string[];
  node_kind: 'POSTING' | 'GROUP' | 'CALCULATED' | 'CONTRA';
  assignable: boolean;
  disabled_reason: string | null;
  sort_order: number;
}

export interface ChartRegistryView {
  schema_version: '2.0';
  registry_digest: string;
  overlay_digest: string;
  locale: string;
  entries: ChartEntry[];
  etag: string;
}

export type AssignmentScope = 'THIS_ONLY' | 'SAME_VENDOR_FUTURE';

export interface AssignmentResponse {
  schema_version: '3.0';
  assignment_id: string;
  txn_id: string;
  state: 'USER_ASSIGNED';
  account_id: string;
  scope: AssignmentScope;
  rule_effect: 'NONE' | 'ACTIVE_USER_RULE_CREATED' | 'EXISTING_USER_RULE_KEPT' | 'ACTIVE_USER_RULE_REPLACED';
  rule_id: string | null;
  transaction_version: number;
  receipt_digest: string;
}

export interface LearnedRule {
  schema_version: '3.0';
  rule_id: string;
  account_id: string;
  source_assignment_id: string;
  state: 'ACTIVE_USER_RULE' | 'INACTIVE_USER' | 'INACTIVE_REGISTRY' | 'DEGRADED_KEY_ROTATION' | 'CONFLICT_REVIEW';
  registry_digest: string;
  overlay_digest: string;
  match_key_id: string;
  normalization_version: string;
  adapter_id: string;
  adapter_version: string;
  direction: 'IN' | 'OUT';
  currency: string;
  created_at: string;
  deactivated_at: string | null;
  resource_version: number;
  descriptor_display: string;
}

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  code: string;
  request_id: string;
  safe_detail: string;
  actions: string[];
  current_version?: number | null;
  conflict_id?: string;
  conflict_version?: number;
  existing_account_id?: string;
  proposed_account_id?: string;
}

export class ContractError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = 'ContractError';
  }
}

function object(value: unknown, code: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ContractError(code);
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, allowed: readonly string[], code: string): void {
  const accepted = new Set(allowed);
  if (Object.keys(value).some(key => !accepted.has(key))) throw new ContractError(code);
}

function string(value: unknown, code: string): string {
  if (typeof value !== 'string') throw new ContractError(code);
  return value;
}

function boolean(value: unknown, code: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(code);
  return value;
}

function number(value: unknown, code: string, minimum = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum) throw new ContractError(code);
  return value;
}

function digest(value: unknown, code: string): string {
  const parsed = string(value, code);
  if (!/^[0-9a-f]{64}$/.test(parsed)) throw new ContractError(code);
  return parsed;
}

function array(value: unknown, code: string): unknown[] {
  if (!Array.isArray(value)) throw new ContractError(code);
  return value;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], code: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) throw new ContractError(code);
  return value as T;
}

export function parseAccountingReviewCapability(value: unknown): AccountingReviewCapabilityStatus {
  const root = object(value, 'CAPABILITY_RESPONSE_INVALID');
  exact(root, ['schema_version', 'capability_id', 'status', 'registered', 'required_routes', 'covered_routes', 'self_test', 'reason_codes', 'verified_at', 'registry_digest', 'overlay_digest', 'event_count', 'evidence_digest'], 'CAPABILITY_UNKNOWN_FIELD');
  if (root.schema_version !== 'butler.accounting_capability_status.v2') throw new ContractError('CAPABILITY_SCHEMA_INVALID');
  return {
    schema_version: 'butler.accounting_capability_status.v2',
    capability_id: oneOf(root.capability_id, ['accounting.user_assignment'] as const, 'CAPABILITY_ID_INVALID'),
    status: oneOf(root.status, [
      'NOT_REGISTERED', 'REGISTERED_NOT_CONSUMED', 'PARTIALLY_CONSUMED',
      'CONSUMED', 'DEGRADED', 'UNAVAILABLE',
    ] as const, 'CAPABILITY_STATUS_INVALID'),
    registered: boolean(root.registered, 'CAPABILITY_REGISTERED_INVALID'),
    required_routes: number(root.required_routes, 'CAPABILITY_REQUIRED_ROUTES_INVALID'),
    covered_routes: number(root.covered_routes, 'CAPABILITY_COVERED_ROUTES_INVALID'),
    self_test: oneOf(root.self_test, ['PASS', 'FAIL', 'NOT_RUN'] as const, 'CAPABILITY_SELF_TEST_INVALID'),
    reason_codes: array(root.reason_codes, 'CAPABILITY_REASONS_INVALID').map(reason => string(reason, 'CAPABILITY_REASON_INVALID')),
    verified_at: string(root.verified_at, 'CAPABILITY_VERIFIED_AT_INVALID'),
    registry_digest: digest(root.registry_digest, 'CAPABILITY_REGISTRY_INVALID'),
    overlay_digest: digest(root.overlay_digest, 'CAPABILITY_OVERLAY_INVALID'),
    event_count: number(root.event_count, 'CAPABILITY_EVENT_COUNT_INVALID'),
    evidence_digest: digest(root.evidence_digest, 'CAPABILITY_EVIDENCE_INVALID'),
  };
}

export function parseSummary(value: unknown): ReviewSummary {
  const root = object(value, 'SUMMARY_INVALID');
  exact(root, ['schema_version', 'batch_id', 'batch_version', 'registry_digest', 'overlay_digest', 'counts', 'total_input_rows', 'generated_at', 'evidence_digest'], 'SUMMARY_UNKNOWN_FIELD');
  if (root.schema_version !== '3.0') throw new ContractError('SUMMARY_SCHEMA_INVALID');
  const counts = object(root.counts, 'SUMMARY_COUNTS_INVALID');
  exact(counts, ['source_declared_valid', 'auto_propose', 'user_rule_applied_draft', 'review_required', 'review_quarantine', 'non_expense_bank_event', 'user_assigned'], 'SUMMARY_COUNTS_UNKNOWN_FIELD');
  return {
    schema_version: '3.0',
    batch_id: string(root.batch_id, 'SUMMARY_BATCH_INVALID'),
    batch_version: number(root.batch_version, 'SUMMARY_VERSION_INVALID'),
    registry_digest: digest(root.registry_digest, 'SUMMARY_REGISTRY_INVALID'),
    overlay_digest: digest(root.overlay_digest, 'SUMMARY_OVERLAY_INVALID'),
    counts: {
      source_declared_valid: number(counts.source_declared_valid, 'SUMMARY_COUNT_INVALID'),
      auto_propose: number(counts.auto_propose, 'SUMMARY_COUNT_INVALID'),
      user_rule_applied_draft: number(counts.user_rule_applied_draft, 'SUMMARY_COUNT_INVALID'),
      review_required: number(counts.review_required, 'SUMMARY_COUNT_INVALID'),
      review_quarantine: number(counts.review_quarantine, 'SUMMARY_COUNT_INVALID'),
      non_expense_bank_event: number(counts.non_expense_bank_event, 'SUMMARY_COUNT_INVALID'),
      user_assigned: number(counts.user_assigned, 'SUMMARY_COUNT_INVALID'),
    },
    total_input_rows: number(root.total_input_rows, 'SUMMARY_TOTAL_INVALID'),
    generated_at: string(root.generated_at, 'SUMMARY_TIME_INVALID'),
    evidence_digest: digest(root.evidence_digest, 'SUMMARY_EVIDENCE_INVALID'),
  };
}

function parseItem(value: unknown): ReviewItem {
  const item = object(value, 'REVIEW_ITEM_INVALID');
  exact(item, ['txn_id', 'transaction_version', 'booked_date', 'money', 'descriptor_display', 'display_policy', 'bank_direction', 'review_state', 'suggestion'], 'REVIEW_ITEM_UNKNOWN_FIELD');
  const money = object(item.money, 'REVIEW_MONEY_INVALID');
  exact(money, ['currency', 'minor_units'], 'REVIEW_MONEY_UNKNOWN_FIELD');
  let suggestion: ReviewItem['suggestion'] = null;
  if (item.suggestion !== null) {
    const raw = object(item.suggestion, 'REVIEW_SUGGESTION_INVALID');
    exact(raw, ['account_id', 'source', 'safe_reason', 'rule_id'], 'REVIEW_SUGGESTION_UNKNOWN_FIELD');
    suggestion = {
      account_id: string(raw.account_id, 'REVIEW_SUGGESTION_ACCOUNT_INVALID'),
      source: oneOf(raw.source, ['AUTO_PROPOSE', 'USER_RULE_APPLIED_DRAFT'] as const, 'REVIEW_SUGGESTION_SOURCE_INVALID'),
      safe_reason: string(raw.safe_reason, 'REVIEW_SUGGESTION_REASON_INVALID'),
      rule_id: raw.rule_id == null ? null : string(raw.rule_id, 'REVIEW_SUGGESTION_RULE_INVALID'),
    };
  }
  return {
    txn_id: string(item.txn_id, 'REVIEW_TXN_INVALID'),
    transaction_version: number(item.transaction_version, 'REVIEW_VERSION_INVALID'),
    booked_date: string(item.booked_date, 'REVIEW_DATE_INVALID'),
    money: { currency: string(money.currency, 'REVIEW_CURRENCY_INVALID'), minor_units: number(money.minor_units, 'REVIEW_AMOUNT_INVALID', Number.MIN_SAFE_INTEGER) },
    descriptor_display: string(item.descriptor_display, 'REVIEW_DISPLAY_INVALID'),
    display_policy: oneOf(item.display_policy, ['PLAIN', 'MASKED', 'RESTRICTED'] as const, 'REVIEW_DISPLAY_POLICY_INVALID'),
    bank_direction: oneOf(item.bank_direction, ['INFLOW', 'OUTFLOW'] as const, 'REVIEW_DIRECTION_INVALID'),
    review_state: oneOf(item.review_state, ['AUTO_PROPOSE', 'USER_RULE_APPLIED_DRAFT', 'REVIEW_REQUIRED'] as const, 'REVIEW_STATE_INVALID'),
    suggestion,
  };
}

export function parsePage(value: unknown): UnaccountedPage {
  const root = object(value, 'REVIEW_PAGE_INVALID');
  exact(root, ['schema_version', 'batch_id', 'batch_version', 'registry_digest', 'overlay_digest', 'items', 'total_count', 'next_cursor', 'etag'], 'REVIEW_PAGE_UNKNOWN_FIELD');
  if (root.schema_version !== '3.0') throw new ContractError('REVIEW_PAGE_SCHEMA_INVALID');
  return {
    schema_version: '3.0',
    batch_id: string(root.batch_id, 'REVIEW_BATCH_INVALID'),
    batch_version: number(root.batch_version, 'REVIEW_BATCH_VERSION_INVALID'),
    registry_digest: digest(root.registry_digest, 'REVIEW_REGISTRY_INVALID'),
    overlay_digest: digest(root.overlay_digest, 'REVIEW_OVERLAY_INVALID'),
    items: array(root.items, 'REVIEW_ITEMS_INVALID').map(parseItem),
    total_count: number(root.total_count, 'REVIEW_TOTAL_INVALID'),
    next_cursor: root.next_cursor == null ? null : string(root.next_cursor, 'REVIEW_CURSOR_INVALID'),
    etag: string(root.etag, 'REVIEW_ETAG_INVALID'),
  };
}

export function parseQuarantinePage(value: unknown): QuarantinedRow[] {
  const root = object(value, 'QUARANTINE_PAGE_INVALID');
  exact(root, ['schema_version', 'batch_id', 'items'], 'QUARANTINE_PAGE_UNKNOWN_FIELD');
  if (root.schema_version !== '3.0') throw new ContractError('QUARANTINE_PAGE_SCHEMA_INVALID');
  const batchId = string(root.batch_id, 'QUARANTINE_BATCH_INVALID');
  return array(root.items, 'QUARANTINE_ITEMS_INVALID').map(value => {
    const item = object(value, 'QUARANTINE_ITEM_INVALID');
    exact(item, ['row_id', 'batch_id', 'source_row_number', 'source_row_fingerprint', 'reason_code', 'state', 'resource_version'], 'QUARANTINE_ITEM_UNKNOWN_FIELD');
    if (item.batch_id !== batchId || item.state !== 'QUARANTINED') throw new ContractError('QUARANTINE_BINDING_INVALID');
    return {
      row_id: string(item.row_id, 'QUARANTINE_ROW_INVALID'),
      batch_id: batchId,
      source_row_number: number(item.source_row_number, 'QUARANTINE_SOURCE_ROW_INVALID', 1),
      source_row_fingerprint: digest(item.source_row_fingerprint, 'QUARANTINE_FINGERPRINT_INVALID'),
      reason_code: oneOf(item.reason_code, ['INVALID_AMOUNT', 'ZERO_AMOUNT_REVIEW', 'INVALID_BOOKING_DATE'] as const, 'QUARANTINE_REASON_INVALID'),
      state: 'QUARANTINED',
      resource_version: number(item.resource_version, 'QUARANTINE_VERSION_INVALID', 1),
    };
  });
}

export function parseRegistry(value: unknown): ChartRegistryView {
  const root = object(value, 'REGISTRY_INVALID');
  exact(root, ['schema_version', 'registry_digest', 'overlay_digest', 'locale', 'entries', 'etag'], 'REGISTRY_UNKNOWN_FIELD');
  if (root.schema_version !== '2.0') throw new ContractError('REGISTRY_SCHEMA_INVALID');
  const entries = array(root.entries, 'REGISTRY_ENTRIES_INVALID').map(rawValue => {
    const raw = object(rawValue, 'REGISTRY_ENTRY_INVALID');
    exact(raw, ['account_id', 'account_code', 'display_name', 'category_path', 'node_kind', 'assignable', 'disabled_reason', 'sort_order'], 'REGISTRY_ENTRY_UNKNOWN_FIELD');
    return {
      account_id: string(raw.account_id, 'REGISTRY_ACCOUNT_INVALID'),
      account_code: raw.account_code == null ? null : string(raw.account_code, 'REGISTRY_CODE_INVALID'),
      display_name: string(raw.display_name, 'REGISTRY_NAME_INVALID'),
      category_path: array(raw.category_path, 'REGISTRY_PATH_INVALID').map(part => string(part, 'REGISTRY_PATH_PART_INVALID')),
      node_kind: oneOf(raw.node_kind, ['POSTING', 'GROUP', 'CALCULATED', 'CONTRA'] as const, 'REGISTRY_KIND_INVALID'),
      assignable: boolean(raw.assignable, 'REGISTRY_ASSIGNABLE_INVALID'),
      disabled_reason: raw.disabled_reason == null ? null : string(raw.disabled_reason, 'REGISTRY_REASON_INVALID'),
      sort_order: number(raw.sort_order, 'REGISTRY_ORDER_INVALID'),
    };
  });
  return {
    schema_version: '2.0',
    registry_digest: digest(root.registry_digest, 'REGISTRY_DIGEST_INVALID'),
    overlay_digest: digest(root.overlay_digest, 'REGISTRY_OVERLAY_INVALID'),
    locale: string(root.locale, 'REGISTRY_LOCALE_INVALID'),
    entries,
    etag: string(root.etag, 'REGISTRY_ETAG_INVALID'),
  };
}

export function parseAssignment(value: unknown): AssignmentResponse {
  const root = object(value, 'ASSIGNMENT_INVALID');
  exact(root, ['schema_version', 'assignment_id', 'txn_id', 'state', 'account_id', 'scope', 'rule_effect', 'rule_id', 'transaction_version', 'receipt_digest'], 'ASSIGNMENT_UNKNOWN_FIELD');
  if (root.schema_version !== '3.0' || root.state !== 'USER_ASSIGNED') throw new ContractError('ASSIGNMENT_SCHEMA_INVALID');
  return {
    schema_version: '3.0',
    assignment_id: string(root.assignment_id, 'ASSIGNMENT_ID_INVALID'),
    txn_id: string(root.txn_id, 'ASSIGNMENT_TXN_INVALID'),
    state: 'USER_ASSIGNED',
    account_id: string(root.account_id, 'ASSIGNMENT_ACCOUNT_INVALID'),
    scope: oneOf(root.scope, ['THIS_ONLY', 'SAME_VENDOR_FUTURE'] as const, 'ASSIGNMENT_SCOPE_INVALID'),
    rule_effect: oneOf(root.rule_effect, [
      'NONE', 'ACTIVE_USER_RULE_CREATED', 'EXISTING_USER_RULE_KEPT', 'ACTIVE_USER_RULE_REPLACED',
    ] as const, 'ASSIGNMENT_RULE_EFFECT_INVALID'),
    rule_id: root.rule_id == null ? null : string(root.rule_id, 'ASSIGNMENT_RULE_INVALID'),
    transaction_version: number(root.transaction_version, 'ASSIGNMENT_VERSION_INVALID'),
    receipt_digest: digest(root.receipt_digest, 'ASSIGNMENT_RECEIPT_INVALID'),
  };
}

export function parseProblem(value: unknown, fallbackStatus: number): ProblemDetail {
  const root = object(value, 'PROBLEM_INVALID');
  exact(root, ['type', 'title', 'status', 'code', 'reason_code', 'detail', 'request_id', 'safe_detail', 'actions', 'current_version', 'conflict_id', 'conflict_version', 'existing_account_id', 'proposed_account_id'], 'PROBLEM_UNKNOWN_FIELD');
  if (root.reason_code !== root.code || root.detail !== root.safe_detail) throw new ContractError('PROBLEM_REASON_MISMATCH');
  return {
    type: string(root.type, 'PROBLEM_TYPE_INVALID'),
    title: string(root.title, 'PROBLEM_TITLE_INVALID'),
    status: typeof root.status === 'number' ? root.status : fallbackStatus,
    code: string(root.code, 'PROBLEM_CODE_INVALID'),
    request_id: string(root.request_id, 'PROBLEM_REQUEST_INVALID'),
    safe_detail: string(root.safe_detail, 'PROBLEM_DETAIL_INVALID'),
    actions: Array.isArray(root.actions) ? root.actions.map(action => String(action)) : [],
    current_version: typeof root.current_version === 'number' ? root.current_version : null,
    conflict_id: typeof root.conflict_id === 'string' ? root.conflict_id : undefined,
    conflict_version: typeof root.conflict_version === 'number' ? root.conflict_version : undefined,
    existing_account_id: typeof root.existing_account_id === 'string' ? root.existing_account_id : undefined,
    proposed_account_id: typeof root.proposed_account_id === 'string' ? root.proposed_account_id : undefined,
  };
}

export function parseRules(value: unknown): LearnedRule[] {
  const root = object(value, 'RULE_LIST_INVALID');
  exact(root, ['schema_version', 'items'], 'RULE_LIST_UNKNOWN_FIELD');
  if (root.schema_version !== '3.0') throw new ContractError('RULE_LIST_SCHEMA_INVALID');
  return array(root.items, 'RULE_ITEMS_INVALID').map(itemValue => {
    const item = object(itemValue, 'RULE_INVALID');
    exact(item, ['schema_version', 'rule_id', 'account_id', 'source_assignment_id', 'state', 'registry_digest', 'overlay_digest', 'match_key_id', 'normalization_version', 'adapter_id', 'adapter_version', 'direction', 'currency', 'created_at', 'deactivated_at', 'resource_version', 'descriptor_display'], 'RULE_UNKNOWN_FIELD');
    return {
      schema_version: '3.0',
      rule_id: string(item.rule_id, 'RULE_ID_INVALID'),
      account_id: string(item.account_id, 'RULE_ACCOUNT_INVALID'),
      source_assignment_id: string(item.source_assignment_id, 'RULE_ASSIGNMENT_INVALID'),
      state: oneOf(item.state, ['ACTIVE_USER_RULE', 'INACTIVE_USER', 'INACTIVE_REGISTRY', 'DEGRADED_KEY_ROTATION', 'CONFLICT_REVIEW'] as const, 'RULE_STATE_INVALID'),
      registry_digest: digest(item.registry_digest, 'RULE_REGISTRY_INVALID'),
      overlay_digest: digest(item.overlay_digest, 'RULE_OVERLAY_INVALID'),
      match_key_id: string(item.match_key_id, 'RULE_KEY_INVALID'),
      normalization_version: string(item.normalization_version, 'RULE_NORMALIZATION_INVALID'),
      adapter_id: string(item.adapter_id, 'RULE_ADAPTER_INVALID'),
      adapter_version: string(item.adapter_version, 'RULE_ADAPTER_VERSION_INVALID'),
      direction: oneOf(item.direction, ['IN', 'OUT'] as const, 'RULE_DIRECTION_INVALID'),
      currency: string(item.currency, 'RULE_CURRENCY_INVALID'),
      created_at: string(item.created_at, 'RULE_CREATED_INVALID'),
      deactivated_at: item.deactivated_at == null ? null : string(item.deactivated_at, 'RULE_DEACTIVATED_INVALID'),
      resource_version: number(item.resource_version, 'RULE_VERSION_INVALID'),
      descriptor_display: string(item.descriptor_display, 'RULE_DISPLAY_INVALID'),
    };
  });
}
