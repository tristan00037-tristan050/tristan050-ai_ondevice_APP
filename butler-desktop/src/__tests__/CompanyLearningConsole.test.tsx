import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { CompanyLearningConsole } from '../components/v1_1/CompanyLearningConsole';

const SELECTED_PATH = '/Users/me/very-secret-client-folder';
const DIGEST = `sha256:${'a'.repeat(64)}`;

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(async () => SELECTED_PATH),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: async () => 'company-learning-cap-token',
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function counters() {
  return {
    scanned_files: 1,
    processed_files: 1,
    skipped_unsupported: 0,
    skipped_hidden: 0,
    skipped_symlink: 0,
    skipped_limit: 0,
    skipped_extractor: 0,
    failed_extract: 0,
    total_bytes: 32,
    chunk_count: 1,
    by_extension: { '.txt': 1 },
  };
}

function makeFetchRouter() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/folder/connect') && method === 'POST') {
      expect(JSON.parse(String(init?.body))).toEqual({ folder_path: SELECTED_PATH });
      return jsonResponse({
        schema_version: 'company_learning.connect.response.v1',
        job_id: 'clj-1',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        counters: counters(),
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/status') && method === 'GET') {
      return jsonResponse({
        schema_version: 'company_learning.status.v1',
        job_id: 'clj-1',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        progress: 100,
        counters: counters(),
        started_at: '2026-06-20T00:00:00Z',
        updated_at: '2026-06-20T00:00:00Z',
        error_code: null,
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/understanding') && method === 'GET') {
      return jsonResponse({
        schema_version: 'company_learning.understanding.v1',
        job_id: 'clj-1',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        integration_mode: 'local_only',
        llm_status: 'not_used',
        doc_type_distribution: [{ type: 'text', extension_digest: DIGEST, count: 1 }],
        topics: [{ topic: 'text_materials', evidence_count: 1 }],
        claims: [
          {
            claim_id: 'claim-local-index-ready',
            claim_runtime_text: '지원 확장자 문서 1개가 이 기기 안에서 인덱싱되었습니다.',
            evidence_chips: [
              {
                schema_version: 'company_learning.file_evidence_chip.v1',
                chunk_digest: DIGEST,
                source_id: 'file:aaaaaaaaaaaaaaaa',
                page_or_sheet: null,
                section_digest: DIGEST,
                char_span: [0, 32],
              },
            ],
          },
        ],
        summary_runtime_text: '로컬 인덱싱 결과: 지원 파일 1개, 청크 1개, 근거 칩 1개를 확인했습니다.',
        needs_review: false,
        needs_review_reason: null,
        evidence_chip_count: 1,
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/handoff') && method === 'POST') {
      return jsonResponse({
        schema_version: 'company_learning.handoff.response.v1',
        job_id: 'clj-1',
        learning_event_id: 'lev-1',
        status: 'CANDIDATE',
        learning_type: 'memory_search',
        approved_text_ref: 'vault://company-learning/aaaaaaaa',
        approved_text_digest: DIGEST,
        sanitized_summary_digest: DIGEST,
        verified_for_training: false,
        policy_decision: 'needs_review',
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    return jsonResponse({}, 404);
  });
}

function makeFetchRouterWithSecondConnectFailure() {
  let connectCount = 0;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/folder/connect') && method === 'POST') {
      connectCount += 1;
      if (connectCount === 2) {
        return jsonResponse({ detail: { fail_class: 'NO_INDEXABLE_FILES', message: 'NO_INDEXABLE_FILES' } }, 422);
      }
      return jsonResponse({
        schema_version: 'company_learning.connect.response.v1',
        job_id: 'clj-1',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        counters: counters(),
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/status') && method === 'GET') {
      return jsonResponse({
        schema_version: 'company_learning.status.v1',
        job_id: 'clj-1',
        status: 'COMPLETED',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        progress: 100,
        counters: counters(),
        started_at: '2026-06-20T00:00:00Z',
        updated_at: '2026-06-20T00:00:00Z',
        error_code: null,
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/understanding') && method === 'GET') {
      return jsonResponse({
        schema_version: 'company_learning.understanding.v1',
        job_id: 'clj-1',
        folder_digest: DIGEST,
        ingest_digest: DIGEST,
        integration_mode: 'local_only',
        llm_status: 'not_used',
        doc_type_distribution: [{ type: 'text', extension_digest: DIGEST, count: 1 }],
        topics: [{ topic: 'text_materials', evidence_count: 1 }],
        claims: [
          {
            claim_id: 'claim-local-index-ready',
            claim_runtime_text: '지원 확장자 문서 1개가 이 기기 안에서 인덱싱되었습니다.',
            evidence_chips: [
              {
                schema_version: 'company_learning.file_evidence_chip.v1',
                chunk_digest: DIGEST,
                source_id: 'file:aaaaaaaaaaaaaaaa',
                page_or_sheet: null,
                section_digest: DIGEST,
                char_span: [0, 32],
              },
            ],
          },
        ],
        summary_runtime_text: '로컬 인덱싱 결과: 지원 파일 1개, 청크 1개, 근거 칩 1개를 확인했습니다.',
        needs_review: false,
        needs_review_reason: null,
        evidence_chip_count: 1,
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    return jsonResponse({}, 404);
  });
}

function applyAuth() {
  fireEvent.change(screen.getByLabelText('Learning Admin ID digest'), { target: { value: DIGEST } });
  fireEvent.change(screen.getByLabelText('Learning Admin session digest'), { target: { value: DIGEST } });
  fireEvent.click(screen.getByTestId('learning-apply-auth-btn'));
}

describe('CompanyLearningConsole', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('connects folder without rendering or persisting the selected path', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem');

    render(<CompanyLearningConsole onClose={() => undefined} />);
    applyAuth();
    fireEvent.click(screen.getByTestId('choose-learning-folder-btn'));

    await waitFor(() => expect(screen.getByTestId('learning-understanding-panel')).toBeInTheDocument());
    expect(screen.getByTestId('learning-job-panel')).toHaveTextContent('지원 파일');
    expect(screen.queryByText(SELECTED_PATH)).not.toBeInTheDocument();
    expect(screen.queryByText(/very-secret-client-folder/)).not.toBeInTheDocument();
    expect(screen.queryByText('학습완료')).not.toBeInTheDocument();
    expect(storageSpy).not.toHaveBeenCalled();

    const chips = screen.getAllByTestId('learning-evidence-chip');
    expect(chips[0]).toHaveTextContent('file:aaaaaaaaaaaaaaaa');
    expect(chips[0]).not.toHaveTextContent('very-secret-client-folder');

    fireEvent.click(screen.getByTestId('learning-handoff-btn'));
    await waitFor(() => expect(screen.getByTestId('learning-handoff-result')).toBeInTheDocument());
    expect(screen.getByTestId('learning-handoff-result')).toHaveTextContent('CANDIDATE');

    const dialog = screen.getByTestId('company-learning-console');
    expect(within(dialog).queryByText(/모든 업무 완전 이해/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/자동 학습 완료/)).not.toBeInTheDocument();
  });

  it('has the packaged Tauri permission needed for the folder picker', () => {
    const capability = JSON.parse(
      readFileSync(resolve(process.cwd(), 'src-tauri/capabilities/default.json'), 'utf8'),
    ) as { permissions: unknown[] };
    expect(capability.permissions).toContain('dialog:allow-open');
  });

  it('clears stale job state when reconnecting to a folder that fails ingest', async () => {
    const fetchMock = makeFetchRouterWithSecondConnectFailure();
    vi.stubGlobal('fetch', fetchMock);
    vi.mocked(openDialog).mockResolvedValue(SELECTED_PATH);

    render(<CompanyLearningConsole onClose={() => undefined} />);
    applyAuth();
    fireEvent.click(screen.getByTestId('choose-learning-folder-btn'));

    await waitFor(() => expect(screen.getByTestId('learning-handoff-btn')).toBeEnabled());
    fireEvent.click(screen.getByTestId('choose-learning-folder-btn'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('인덱싱할 수 있는 지원 파일이 없습니다.'));
    expect(screen.queryByTestId('learning-job-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('learning-understanding-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('learning-handoff-btn')).not.toBeInTheDocument();
  });
});
