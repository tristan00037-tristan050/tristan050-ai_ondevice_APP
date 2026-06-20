import type { AdminContextForSidecar } from '../company_fact/contracts';

export type { AdminContextForSidecar };

export const COMPANY_LEARNING_ENDPOINTS = {
  connectFolder: '/v1/company-learning/folder/connect',
  status: (jobId: string) => `/v1/company-learning/status?job_id=${encodeURIComponent(jobId)}`,
  understanding: (jobId: string) => `/v1/company-learning/understanding?job_id=${encodeURIComponent(jobId)}`,
  handoff: '/v1/company-learning/handoff',
} as const;

export type CompanyLearningCounters = {
  scanned_files: number;
  processed_files: number;
  skipped_unsupported: number;
  skipped_hidden: number;
  skipped_symlink: number;
  skipped_limit: number;
  skipped_extractor: number;
  failed_extract: number;
  total_bytes: number;
  chunk_count: number;
  by_extension: Record<string, number>;
};

export type CompanyLearningConnectResponse = {
  schema_version: 'company_learning.connect.response.v1';
  job_id: string;
  status: string;
  folder_digest: `sha256:${string}`;
  ingest_digest: `sha256:${string}`;
  counters: CompanyLearningCounters;
  raw_text_logged: false;
  external_send_zero: true;
};

export type CompanyLearningStatusResponse = {
  schema_version: 'company_learning.status.v1';
  job_id: string;
  status: string;
  folder_digest: `sha256:${string}`;
  ingest_digest: `sha256:${string}`;
  progress: number;
  counters: CompanyLearningCounters;
  started_at: string;
  updated_at: string;
  error_code: string | null;
  raw_text_logged: false;
  external_send_zero: true;
};

export type CompanyLearningEvidenceChip = {
  schema_version: 'company_learning.file_evidence_chip.v1';
  chunk_digest: `sha256:${string}`;
  source_id: string;
  page_or_sheet: number | null;
  section_digest: `sha256:${string}`;
  char_span: [number, number];
};

export type CompanyLearningClaim = {
  claim_id: string;
  claim_runtime_text: string;
  evidence_chips: CompanyLearningEvidenceChip[];
};

export type CompanyLearningUnderstanding = {
  schema_version: 'company_learning.understanding.v1';
  job_id: string;
  folder_digest: `sha256:${string}`;
  ingest_digest: `sha256:${string}`;
  integration_mode: 'local_only';
  llm_status: 'ready' | 'no_model' | 'error' | 'not_used';
  doc_type_distribution: Array<{ type: string; extension_digest: `sha256:${string}`; count: number }>;
  topics: Array<{ topic: string; evidence_count: number }>;
  claims: CompanyLearningClaim[];
  summary_runtime_text: string;
  needs_review: boolean;
  needs_review_reason: string | null;
  evidence_chip_count: number;
  raw_text_logged: false;
  external_send_zero: true;
};

export type CompanyLearningHandoffResponse = {
  schema_version: 'company_learning.handoff.response.v1';
  job_id: string;
  learning_event_id: string;
  status: 'CANDIDATE';
  learning_type: 'memory_search';
  approved_text_ref: string;
  approved_text_digest: `sha256:${string}`;
  sanitized_summary_digest: `sha256:${string}`;
  verified_for_training: false;
  policy_decision: 'needs_review';
  raw_text_logged: false;
  external_send_zero: true;
};

export type SidecarErrorPayload = {
  fail_class: string;
  message: string;
};
