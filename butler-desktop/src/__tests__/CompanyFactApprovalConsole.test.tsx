import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { CompanyFactApprovalConsole } from '../components/v1_1/CompanyFactApprovalConsole';

// 기존 sidecar capability token 취득 방식(invoke)을 plain 함수로 모킹(resetAllMocks 영향 없음).
vi.mock('@tauri-apps/api/core', () => ({
  invoke: async () => 'cap-token',
}));

const DIGEST = `sha256:${'a'.repeat(64)}`;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const DETAIL = {
  fact_id: 'F1',
  status: 'CANDIDATE',
  category: '휴가 규정',
  question_patterns: ['연차 며칠'],
  keywords_required: ['연차'],
  keywords_any: ['휴가'],
  source: '인사팀',
  source_doc: 'hr.pdf',
  verified_at: null,
  expires_at: null,
  confidence: 0.9,
  answer_runtime_text: '연차는 15일입니다.',
  raw_text_logged: false,
  external_send_zero: true,
};

const INDEX_ROW = {
  fact_id: 'F1',
  status: 'CANDIDATE',
  category: '휴가 규정',
  question_patterns: ['연차 며칠'],
  keywords_required: ['연차'],
  keywords_any: ['휴가'],
  source: '인사팀',
  source_doc: 'hr.pdf',
  verified_at: null,
  expires_at: null,
  confidence: 0.9,
};

/** url/method 기반 응답 라우터. */
function makeFetchRouter(overrides: { listStatus?: number; listBody?: unknown } = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/approve') && method === 'POST') {
      return jsonResponse({ fact_id: 'F1', status: 'ACTIVE', raw_text_logged: false, external_send_zero: true });
    }
    if (url.includes('/deprecate') && method === 'POST') {
      return jsonResponse({ fact_id: 'F1', status: 'DEPRECATED', raw_text_logged: false, external_send_zero: true });
    }
    if (url.includes('/v1/company-facts/status')) {
      return jsonResponse({ active_count: 1, candidate_count: 1, raw_text_logged: false, external_send_zero: true });
    }
    if (/\/v1\/company-facts\/candidates\/F1$/.test(url)) {
      return jsonResponse(DETAIL);
    }
    if (url.includes('/v1/company-facts/candidates')) {
      if (overrides.listStatus && overrides.listStatus >= 400) {
        return jsonResponse(overrides.listBody ?? {}, overrides.listStatus);
      }
      return jsonResponse({ candidates: [INDEX_ROW], raw_text_logged: false, external_send_zero: true });
    }
    return jsonResponse({}, 404);
  });
}

function applyAuth() {
  fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
  fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
  fireEvent.click(screen.getByTestId('apply-auth-btn'));
}

function countPost(fetchMock: ReturnType<typeof vi.fn>, marker: string): number {
  return fetchMock.mock.calls.filter(
    ([url, init]) => String(url).includes(marker) && (init as RequestInit | undefined)?.method === 'POST',
  ).length;
}

function countCandidateDetailGets(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    ([url, init]) => /\/v1\/company-facts\/candidates\/F1$/.test(String(url)) && (init as RequestInit | undefined)?.method === 'GET',
  ).length;
}

describe('CompanyFactApprovalConsole', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads list + status, then opens detail with answer_runtime_text on row click', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();

    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    expect(screen.getByTestId('company-fact-status')).toHaveTextContent('ACTIVE 1');

    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());
    expect(screen.getByTestId('answer-runtime-text')).toHaveTextContent('연차는 15일입니다.');
  });

  it('approve modal: 0 POST before confirm, 1 POST after confirm, then status refetch', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();
    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('approve-btn'));
    const modal = await screen.findByTestId('confirm-modal');
    expect(within(modal).getByText(/회사 공식 지식으로 승인/)).toBeInTheDocument();
    expect(countPost(fetchMock, '/approve')).toBe(0);

    const statusCallsBefore = fetchMock.mock.calls.filter(([u]) => String(u).includes('/status')).length;
    const detailGetsBefore = countCandidateDetailGets(fetchMock);
    fireEvent.click(screen.getByTestId('confirm-ok-btn'));

    await waitFor(() => expect(countPost(fetchMock, '/approve')).toBe(1));
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/status')).length).toBeGreaterThan(statusCallsBefore),
    );
    expect(countCandidateDetailGets(fetchMock)).toBe(detailGetsBefore);
    expect(screen.queryByTestId('candidate-detail')).not.toBeInTheDocument();
  });

  it('deprecate modal: 0 POST before confirm, 1 POST after confirm', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();
    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('deprecate-btn'));
    const modal = await screen.findByTestId('confirm-modal');
    expect(within(modal).getByText(/폐기하시겠습니까/)).toBeInTheDocument();
    expect(countPost(fetchMock, '/deprecate')).toBe(0);

    fireEvent.click(screen.getByTestId('confirm-ok-btn'));
    await waitFor(() => expect(countPost(fetchMock, '/deprecate')).toBe(1));
  });

  it('maps backend fail_class to a human message', async () => {
    const fetchMock = makeFetchRouter({
      listStatus: 403,
      listBody: { detail: { fail_class: 'ADMIN_ROLE_NOT_REGISTERED', message: 'raw backend text' } },
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('현재 계정은 등록된 팀장/관리자가 아닙니다.');
    // raw backend 메시지는 렌더링하지 않는다(allowlist).
    expect(screen.queryByText(/raw backend text/)).not.toBeInTheDocument();
  });

  it('blocks zero-digest before any fetch and shows placeholder message', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: `sha256:${'0'.repeat(64)}` } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.click(screen.getByTestId('apply-auth-btn'));

    expect(await screen.findByRole('alert')).toHaveTextContent('임시 관리자 식별값은 사용할 수 없습니다');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('raw-0: never writes to console/localStorage/sessionStorage during the approve flow', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const lsSpy = vi.spyOn(Storage.prototype, 'setItem');

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();
    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('approve-btn'));
    fireEvent.click(await screen.findByTestId('confirm-ok-btn'));
    await waitFor(() => expect(countPost(fetchMock, '/approve')).toBe(1));

    expect(logSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
    expect(lsSpy).not.toHaveBeenCalled();
  });
});
