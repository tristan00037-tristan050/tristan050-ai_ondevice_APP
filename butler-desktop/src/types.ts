export interface SSEEvent {
  type:
    | 'meta'
    | 'phase_start'
    | 'chunk'
    | 'chunk_progress'
    | 'chunk_done'
    | 'reduce_start'
    | 'verify_start'
    | 'complete'
    | 'error'
    | 'cancelled'
    | 'heartbeat';
  data: Record<string, unknown>;
}

export interface EgressStats {
  task_id: string;
  mode: 'local_only' | 'network_allowed';
  egress_bytes_total: number;
  dns_requests: number;
  http_requests: number;
  https_requests: number;
  telemetry_enabled: boolean;
  crash_report_enabled: boolean;
  update_check_enabled: boolean;
  raw_text_logged: boolean;
  input_digest16: string;
  output_digest16: string;
  verdict: 'PASS' | 'FAIL';
}

export type FileGrade = 'S' | 'M' | 'L' | 'XL' | 'Media-L' | 'blocked';

export interface Message {
  id: string;
  role: 'user' | 'butler';
  content: string;
  timestamp: string;
  /** Durable one-based sequence assigned by the product store. */
  sequence?: number;
  source?: 'factpack' | 'llm';
  fact_id?: string;
  score?: number;
}

export interface Conversation {
  id: string;
  title: string;
  title_is_custom: boolean;
  created_at: string;
  updated_at: string;
  messages: Message[];
  folder_id?: string;
  version?: number;
  business_profile_id?: string | null;
  message_count?: number;
  deleted_at?: string | null;
  locked?: boolean;
}

export type HomeStartupState =
  | 'NEW_INSTALL_READY'
  | 'HOME_READY'
  | 'READ_ONLY_WORKSPACE_MIRROR_MISSING'
  | 'READ_ONLY_WORKSPACE_CONFLICT'
  | 'READ_ONLY_KEY_MISSING'
  | 'READ_ONLY_KEY_ID_CONFLICT'
  | 'READ_ONLY_DB_INTEGRITY_FAILED'
  | 'READ_ONLY_STORAGE_GUARD_FAILED'
  | 'MIGRATION_REQUIRED'
  | 'MIGRATION_BLOCKED';

export interface HomeStartupStatus {
  schema_version: '2.1.0';
  status: HomeStartupState;
  read_only: boolean;
  mutation_allowed: boolean;
  model_execution_allowed: boolean;
  existing_conversation_count: number;
  support_code: string;
  checked_at: string;
  tree_oid: string;
}

export interface FolderRecord {
  folder_id: string;
  parent_id: string | null;
  display_name: string;
  system_kind: 'UNCLASSIFIED' | 'TRASH' | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface HomeSnapshot {
  schema_version: 'butler.home.snapshot.v2';
  workspace_id: string;
  folders: FolderRecord[];
  conversations: Conversation[];
  next_cursor: string | null;
  partial_errors: Array<{ conversation_id: string; code: string }>;
  read_only: boolean;
  startup: HomeStartupStatus;
  total_conversation_count: number;
  filtered_conversation_count: number;
  inventory_digest: string;
  active_profile_filter?: string | null;
}

export type HomeInventoryState = 'LOADING' | 'PARTIAL' | 'LOCKED' | 'ERROR' | 'COMPLETE';

export interface ConversationMessageInventory {
  state: Exclude<HomeInventoryState, 'LOADING'>;
  messages: Message[];
  expected_count: number;
  loaded_count: number;
  next_sequence: number | null;
  error_code: string | null;
}

export interface RuntimeStatus {
  schema_version: '2.1.0';
  policy: { status: 'KNOWN' | 'UNKNOWN' | 'UNAVAILABLE'; source: string | null; digest: string | null };
  measurement: {
    status: 'NOT_MEASURED' | 'PASS' | 'FAIL' | 'UNKNOWN' | 'UNAVAILABLE';
    source: string | null;
    receipt_digest: string | null;
    measured_at: string | null;
    fresh: boolean | null;
  };
  runtime_activation_allowed: false;
  generated_at: string;
}

export interface RuntimeTrustReceipt {
  schema_version: 'butler.firstscreen.native-trust-receipt.v2';
  status: 'VERIFIED_AND_COMMITTED';
  error_code: 'OK';
  request_id: string;
  generation_before: number;
  generation_after: number;
  old_root_digest: string | null;
  new_root_digest: string;
  root_version: number;
  revocation_version: number;
  revocation_digest: string;
  valid_old_root_signer_ids: string[];
  valid_new_root_signer_ids: string[];
  valid_revocation_signer_ids: string[];
  rejected_envelope_count: number;
  rejected_envelope_reasons: string[];
  source_commit_oid: string;
  source_tree_oid: string;
  native_build_identity_digest: string;
  committed_state_digest: string;
  previous_receipt_digest: string | null;
  issued_at_utc: string;
  runtime_activation_allowed: false;
  receipt_digest: string;
}

export interface RuntimeTrustStatus {
  schema_version: 'butler.firstscreen.runtime-trust-status.v1';
  authority: 'rust-native';
  configured: boolean;
  generation: number;
  root_digest: string | null;
  root_version: number | null;
  revocation_digest: string | null;
  revocation_version: number | null;
  previous_trusted_state_receipt_digest: string | null;
  runtime_activation_allowed: false;
}

export interface RuntimeTrustCandidate {
  schema_version: 'butler.firstscreen.trust-candidate.v2';
  environment: 'development' | 'release';
  root_json: string;
  revocations_json: string;
  decision_json: string;
  release_subjects_json: string;
  source_commit_oid: string;
  source_tree_oid: string;
  native_build_identity_digest: string;
  runtime_activation_allowed: false;
}

export interface TurnCorrelation {
  schema_version: '2.1.0';
  turn_id: string;
  model_request_id: string;
  conversation_id: string;
  conversation_version: number;
  version: number;
  folder_id: string;
  request_id: string;
  durable: true;
}

export interface MigrationReceipt {
  schema_version: 'butler.home.migration.receipt.v2';
  migration_id: string;
  input_digest: string;
  id_set_digest: string;
  item_count: number;
  inserted: Array<{id:string;digest:string}>;
  identical_existing: Array<{id:string;digest:string}>;
  conflicts: Array<{id:string;digest:string}>;
  exact_import: boolean;
}
