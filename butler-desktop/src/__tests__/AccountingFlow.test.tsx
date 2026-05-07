import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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
    vi.restoreAllMocks();
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
    }, { timeout: 2000 });
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
    }, { timeout: 2000 });

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

  it('test_download_btn_fetches_xlsx_blob_and_triggers_save', async () => {
    // 다운로드 버튼 클릭 시 올바른 URL로 fetch + DOM 첨부 앵커 클릭 트리거 검증
    // (real timers: MIN_PHASE_MS 800ms 자연 경과 후 done 상태에서 다운로드 검증)
    const xlsxBlob = new Blob(['PK\x03\x04'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }) // classify
      .mockResolvedValueOnce({ ok: true, blob: async () => xlsxBlob });         // download
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    // MIN_PHASE_MS(800ms) 경과 후 done 상태 대기
    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 2000 });

    // DOM spies는 React 마운팅 이후 설치해야 render()가 정상 동작함
    const createObjURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-xlsx-url');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation(node => node as Node);
    vi.spyOn(document.body, 'removeChild').mockImplementation(node => node as Node);

    // Click download button
    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    // Verify xlsx fetch called with correct result_id URL
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    const [xlsxUrl] = mockFetch.mock.calls[1] as [string];
    expect(xlsxUrl).toContain('/accounting/result/test-uuid-1234/xlsx');

    // Verify anchor was appended to DOM (Tauri WKWebView 수정 핵심)
    const appendedAnchor = appendChildSpy.mock.calls.find(
      call => (call[0] as HTMLElement)?.tagName === 'A'
    )?.[0] as HTMLAnchorElement | undefined;
    expect(appendedAnchor).toBeDefined();
    expect(appendedAnchor?.download).toBe('butler_accounting_result.xlsx');
    expect(appendedAnchor?.href).toBe('blob:mock-xlsx-url');
    createObjURLSpy.mockRestore();
  });

  it('test_phase_start_minimum_800ms_display', async () => {
    // phase_start 직후 complete 도착해도 processing 상태가 done 전환 전에 표시됨을 검증
    // (fake timers: 800ms 타이머를 수동으로 진행해 상태 전환 시점 검증)
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),
    });
    vi.stubGlobal('fetch', mockFetch);

    // render 먼저 — React 18 스케줄러가 타이머를 사용하므로 useFakeTimers 이전
    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    // fake timers 설치 후 파일 처리 시작
    vi.useFakeTimers();
    try {
      fireEvent.change(input);

      // 마이크로태스크 플러시: SSE 파싱 + MIN_PHASE_MS 타이머 등록 (setTimeout 미실행)
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 800ms 이전: processing 상태 유지
      expect(screen.getByTestId('accounting-processing')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-result')).not.toBeInTheDocument();

      // 800ms 경과 → MIN_PHASE_MS 타이머 해제 → done 상태 전환
      await vi.advanceTimersByTimeAsync(800);
      for (let i = 0; i < 10; i++) await Promise.resolve();

      expect(screen.getByTestId('accounting-result')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-processing')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
