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
  question_patterns: ['연차 며칠', '연차 일수'],
  keywords_required: ['연차'],
  keywords_any: ['휴가'],
  source: '인사팀',
  source_url: null,
  source_doc: 'hr.pdf',
  verified_at: null,
  expires_at: null,
  confidence: 0.9,
  fact_digest: `sha256:${'b'.repeat(64)}`,
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
  source_url: null,
  source_doc: 'hr.pdf',
  verified_at: null,
  expires_at: null,
  confidence: 0.9,
  fact_digest: `sha256:${'b'.repeat(64)}`,
};

const KNOWN_BAD = {
  known_bad_suspected: true,
  override_available: true,
  override_active: false,
  match_score: 0.7,
  matched_keywords_count: 1,
  matched_pattern_digest: `sha256:${'c'.repeat(64)}`,
  bad_entry_id: 'bad-1',
  bad_fact_digest: `sha256:${'d'.repeat(64)}`,
  raw_text_logged: false,
  external_send_zero: true,
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
    if (url.includes('/supersede') && method === 'POST') {
      return jsonResponse({
        schema_version: 'company_fact.supersede.result.v1',
        old_fact_id: 'F1',
        old_status: 'DEPRECATED',
        old_fact_digest: DETAIL.fact_digest,
        new_fact_id: 'F2',
        new_status: 'ACTIVE',
        new_fact_digest: `sha256:${'9'.repeat(64)}`,
        previous_fact_digest: DETAIL.fact_digest,
        audit_refs: [`sha256:${'8'.repeat(64)}`],
        raw_text_logged: false,
        external_send_zero: true,
      });
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

function makeKnownBadFetchRouter() {
  let overridePosted = false;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/known-bad/override') && method === 'POST') {
      overridePosted = true;
      return jsonResponse({
        schema_version: 'company_fact.known_bad_override.v1',
        fact_id: 'F1',
        candidate_fact_digest: DETAIL.fact_digest,
        bad_entry_id: 'bad-1',
        bad_fact_digest: KNOWN_BAD.bad_fact_digest,
        approved_by_digest: DIGEST,
        approved_at: '2026-06-20T00:00:00Z',
        status: 'ACTIVE',
        override_digest: `sha256:${'e'.repeat(64)}`,
        audit_ref: `sha256:${'f'.repeat(64)}`,
        raw_text_logged: false,
        external_send_zero: true,
      });
    }
    if (url.includes('/approve') && method === 'POST') {
      if (!overridePosted) {
        return jsonResponse({ detail: { fail_class: 'KNOWN_BAD_APPROVAL_BLOCKED', message: 'blocked' } }, 409);
      }
      return jsonResponse({ fact_id: 'F1', status: 'ACTIVE', raw_text_logged: false, external_send_zero: true });
    }
    if (url.includes('/v1/company-facts/status')) {
      return jsonResponse({ active_count: 1, candidate_count: overridePosted ? 0 : 1, raw_text_logged: false, external_send_zero: true });
    }
    if (/\/v1\/company-facts\/candidates\/F1$/.test(url)) {
      return jsonResponse({ ...DETAIL, known_bad: { ...KNOWN_BAD, override_active: overridePosted } });
    }
    if (url.includes('/v1/company-facts/candidates')) {
      return jsonResponse({ candidates: [{ ...INDEX_ROW, known_bad: KNOWN_BAD }], raw_text_logged: false, external_send_zero: true });
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
    expect(screen.getByTestId('company-fact-status')).toHaveTextContent('사용 중 1개 · 승인 대기 1개');

    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());
    expect(screen.getByTestId('answer-runtime-text')).toHaveTextContent('연차는 15일입니다.');

    // 쉬운 용어: 내부 ID/영어 enum/개발자 용어가 화면에 보이지 않는다.
    const detail = screen.getByTestId('candidate-detail');
    expect(detail).toHaveTextContent('상태');
    expect(detail).toHaveTextContent('승인 대기');
    expect(detail).not.toHaveTextContent('fact_id');
    expect(detail).not.toHaveTextContent('F1');
    expect(detail).not.toHaveTextContent(/CANDIDATE|answer_runtime_text|confidence/);
    expect(screen.getByTestId('company-fact-status')).not.toHaveTextContent(/ACTIVE|CANDIDATE/);
    expect(screen.getByTestId('auth-status')).not.toHaveTextContent('role: admin');
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
    fireEvent.change(screen.getByTestId('deprecate-reason-select'), { target: { value: 'WRONG' } });
    // 사유 옵션과 안내는 한국어로 보인다(영문 enum 비노출).
    expect(within(modal).getByRole('option', { name: '틀린 정보' })).toBeInTheDocument();
    expect(within(modal).queryByRole('option', { name: 'WRONG' })).not.toBeInTheDocument();
    expect(screen.getByTestId('deprecate-reason-copy')).toHaveTextContent('앞으로 비슷한 후보가 들어오면 다시 확인합니다.');
    expect(countPost(fetchMock, '/deprecate')).toBe(0);

    fireEvent.click(screen.getByTestId('confirm-ok-btn'));
    await waitFor(() => expect(countPost(fetchMock, '/deprecate')).toBe(1));
    const deprecateCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/deprecate'));
    const parsed = JSON.parse(String((deprecateCall?.[1] as RequestInit).body));
    expect(parsed).toEqual({ reason_code: 'WRONG' });
  });

  it('known-bad approve 409 keeps confirmation open, then override reloads detail and approves', async () => {
    const fetchMock = makeKnownBadFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();
    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    expect(screen.getByTestId('known-bad-badge-F1')).toHaveTextContent('재검토 필요');
    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());
    expect(screen.getByTestId('known-bad-warning-F1')).toHaveTextContent(
      '재검토 필요: 이전에 틀린 정보로 표시된 항목과 핵심어/패턴이 비슷합니다.',
    );
    // 'override' 같은 개발자 용어는 화면에 보이지 않는다.
    expect(screen.getByTestId('known-bad-warning-F1')).not.toHaveTextContent(/WRONG|override/i);
    expect(screen.queryByTestId('detail-override-and-approve-btn')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('approve-btn'));
    fireEvent.click(await screen.findByTestId('confirm-ok-btn'));

    const modal = await screen.findByTestId('confirm-modal');
    expect(modal).toBeInTheDocument();
    expect(await screen.findByTestId('override-and-approve-btn')).toBeInTheDocument();
    expect(countPost(fetchMock, '/approve')).toBe(1);

    fireEvent.click(screen.getByTestId('override-and-approve-btn'));
    await waitFor(() => expect(countPost(fetchMock, '/known-bad/override')).toBe(1));
    await waitFor(() => expect(countPost(fetchMock, '/approve')).toBe(2));
    await waitFor(() => expect(screen.getByTestId('session-active-fact-panel')).toBeInTheDocument());
    expect(countCandidateDetailGets(fetchMock)).toBeGreaterThanOrEqual(2);
  });

  it('supersede is available only for the just-approved active fact and sends confidence 1.0', async () => {
    const fetchMock = makeFetchRouter();
    vi.stubGlobal('fetch', fetchMock);

    render(<CompanyFactApprovalConsole onClose={() => undefined} />);
    applyAuth();
    await waitFor(() => expect(screen.getByTestId('candidate-row-F1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('candidate-row-F1'));
    await waitFor(() => expect(screen.getByTestId('candidate-detail')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('approve-btn'));
    fireEvent.click(await screen.findByTestId('confirm-ok-btn'));
    await waitFor(() => expect(screen.getByTestId('session-active-fact-panel')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('open-supersede-btn'));
    await waitFor(() => expect(screen.getByTestId('supersede-modal')).toBeInTheDocument());
    // 교체 모달은 쉬운 한국어 라벨만 노출한다(answer_runtime_text 등 내부 용어 없음).
    const supersede = screen.getByTestId('supersede-modal');
    expect(supersede).not.toHaveTextContent(/answer_runtime_text|question_patterns|ACTIVE|confidence/);
    fireEvent.change(screen.getByLabelText('답변 내용'), { target: { value: '연차는 입사일 기준으로 15일입니다.' } });
    fireEvent.click(screen.getByTestId('supersede-submit-btn'));

    await waitFor(() => expect(countPost(fetchMock, '/supersede')).toBe(1));
    const supersedeCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/supersede'));
    const parsed = JSON.parse(String((supersedeCall?.[1] as RequestInit).body));
    expect(parsed.confidence).toBe(1.0);
    expect(parsed.question_patterns).toEqual(['연차 며칠', '연차 일수']);
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
