import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AccountingModal } from '../components/chat/AccountingModal';

// SSE 응답 헬퍼
function makeSseStream(events: Array<{ event: string; data: object }>): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const body = events
    .map(e => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join('');
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
}

const MOCK_SUMMARY = {
  total_rows: 10,
  classified_rows: 9,
  unclassified_rows: 1,
  categories: { 급여: { count: 5, avg_confidence: 0.95 } },
  avg_confidence: 0.9,
};

const SSE_EVENTS_OK = [
  { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
  { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
  {
    event: 'complete',
    data: {
      result_id: 'test-uuid-1234',
      md_content: '## 보고서\n\n총 10건 분류됨.',
      summary: MOCK_SUMMARY,
      row_count: 10,
      category_count: 1,
    },
  },
];

describe('AccountingModal — 업로드 흐름', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('test_modal_renders_drop_zone', () => {
    render(<AccountingModal onClose={() => {}} />);
    expect(screen.getByTestId('accounting-modal')).toBeInTheDocument();
    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
  });

  it('test_file_input_accept_constraint', () => {
    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    expect(input.accept).toBe('.xlsx,.xls,.csv');
  });

  it('test_close_button_calls_onClose', () => {
    const onClose = vi.fn();
    render(<AccountingModal onClose={onClose} />);
    fireEvent.click(screen.getByTestId('accounting-modal-close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('test_overlay_click_calls_onClose', () => {
    const onClose = vi.fn();
    render(<AccountingModal onClose={onClose} />);
    fireEvent.click(screen.getByTestId('accounting-modal-overlay'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('test_invalid_extension_shows_error', async () => {
    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['data'], 'test.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);
    await waitFor(() => {
      expect(screen.getByTestId('accounting-error')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-error').textContent).toContain('.pdf');
  });

  it('test_valid_file_triggers_api_call', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col1\nval1'], 'transactions.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledOnce();
    });
    const [url, opts] = mockFetch.mock.calls[0] as [string, RequestInit & { body: FormData }];
    expect(url).toContain('/accounting/classify');
    expect(opts.method).toBe('POST');
  });

  it('test_processing_state_shows_loading_icon', async () => {
    // fetch가 절대 resolve되지 않는 프로미스를 반환
    const mockFetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['data'], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-processing')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-loading-icon')).toBeInTheDocument();
  });

  it('test_complete_event_shows_result', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-result')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-download-btn')).toBeInTheDocument();
    expect(screen.getByTestId('accounting-report-toggle')).toBeInTheDocument();
    expect(screen.getByTestId('accounting-result').textContent).toContain('10건');
  });

  it('test_report_toggle_shows_markdown', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-report-toggle')).toBeInTheDocument();
    });

    // 보고서 닫힌 상태
    expect(screen.queryByTestId('accounting-report-content')).not.toBeInTheDocument();

    // 토글 클릭
    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    expect(screen.getByTestId('accounting-report-content')).toBeInTheDocument();
    expect(screen.getByTestId('accounting-report-content').textContent).toContain('보고서');

    // 다시 토글 → 닫힘
    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    expect(screen.queryByTestId('accounting-report-content')).not.toBeInTheDocument();
  });

  it('test_server_error_shows_error_state', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: async () => '지원하지 않는 파일 형식',
      statusText: 'Unprocessable Entity',
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['data'], 'test.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-error')).toBeInTheDocument();
    });
  });

  it('test_retry_button_resets_to_idle', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => '서버 오류',
      statusText: 'Server Error',
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['data'], 'test.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-retry-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('accounting-retry-btn'));
    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
  });

  it('test_sse_early_close_without_complete_shows_error', async () => {
    // complete/error 이벤트 없이 스트림이 닫히는 경우 → error 상태 + 메시지 노출
    const encoder = new TextEncoder();
    const abruptStream = new ReadableStream<Uint8Array>({
      start(controller) {
        // phase_start만 보내고 complete 없이 종료
        controller.enqueue(encoder.encode('event: phase_start\ndata: {"status_message":"분류 중"}\n\n'));
        controller.close();
      },
    });

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: abruptStream,
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-error')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-error').textContent).toContain('예기치 않게 종료');
  });

  it('test_modal_guide_text_contains_xlsx_csv', () => {
    // 모달 안내 문구가 .xlsx, .csv 텍스트를 포함하는지 확인
    render(<AccountingModal onClose={() => {}} />);
    const zone = screen.getByTestId('accounting-drop-zone');
    expect(zone.textContent).toContain('.xlsx');
    expect(zone.textContent).toContain('.csv');
  });

  it('test_file_delete_button_resets_to_idle', async () => {
    // 파일 첨부 후 × 버튼 클릭 → 첨부 상태 초기화 (drop zone 복귀)
    const mockFetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'transactions.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    // processing 상태 진입 확인
    await waitFor(() => {
      expect(screen.getByTestId('accounting-selected-file')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-selected-file').textContent).toContain('transactions.xlsx');

    // × 버튼 클릭 → idle 복귀
    const deleteBtn = screen.getByTestId('accounting-file-delete-btn');
    expect(deleteBtn).toHaveAttribute('aria-label', '첨부 파일 삭제');
    fireEvent.click(deleteBtn);

    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
    expect(screen.queryByTestId('accounting-selected-file')).not.toBeInTheDocument();
  });
});
