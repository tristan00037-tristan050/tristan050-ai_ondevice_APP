// Tauri plugin 모킹 — vi.mock은 Vitest에 의해 import보다 먼저 hoisting됨
vi.mock('@tauri-apps/plugin-dialog', () => ({
  save: vi.fn(),
}));
vi.mock('@tauri-apps/plugin-fs', () => ({
  writeFile: vi.fn(),
}));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { save as tauriSave } from '@tauri-apps/plugin-dialog';
import { writeFile as tauriWriteFile } from '@tauri-apps/plugin-fs';
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
  categories: {
    '급여': { count: 5, avg_confidence: 0.95, total_amount: 12500000 },
    '통신비': { count: 4, avg_confidence: 0.88, total_amount: 524300 },
  },
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
      category_count: 2,
    },
  },
];

describe('AccountingModal — 업로드 흐름', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.mocked(tauriSave).mockReset();
    vi.mocked(tauriWriteFile).mockReset();
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
    }, { timeout: 3000 });
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
    }, { timeout: 3000 });

    expect(screen.queryByTestId('accounting-report-content')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    expect(screen.getByTestId('accounting-report-content')).toBeInTheDocument();
    expect(screen.getByTestId('accounting-report-content').textContent).toContain('보고서');

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
    const encoder = new TextEncoder();
    const abruptStream = new ReadableStream<Uint8Array>({
      start(controller) {
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
    render(<AccountingModal onClose={() => {}} />);
    const zone = screen.getByTestId('accounting-drop-zone');
    expect(zone.textContent).toContain('.xlsx');
    expect(zone.textContent).toContain('.csv');
  });

  it('test_file_delete_button_resets_to_idle', async () => {
    const mockFetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'transactions.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('accounting-selected-file')).toBeInTheDocument();
    });
    expect(screen.getByTestId('accounting-selected-file').textContent).toContain('transactions.xlsx');

    const deleteBtn = screen.getByTestId('accounting-file-delete-btn');
    expect(deleteBtn).toHaveAttribute('aria-label', '첨부 파일 삭제');
    fireEvent.click(deleteBtn);

    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
    expect(screen.queryByTestId('accounting-selected-file')).not.toBeInTheDocument();
  });

  it('test_download_btn_uses_tauri_dialog_and_fs', async () => {
    // Tauri v2 표준 다운로드: save dialog + writeFile 호출 검증
    const xlsxBuffer = new ArrayBuffer(4);
    new Uint8Array(xlsxBuffer).set([0x50, 0x4B, 0x03, 0x04]);

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) })       // classify
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => xlsxBuffer });     // download
    vi.stubGlobal('fetch', mockFetch);

    vi.mocked(tauriSave).mockResolvedValueOnce('/tmp/butler_accounting_result.xlsx');
    vi.mocked(tauriWriteFile).mockResolvedValueOnce(undefined);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 3000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    // fetch 2회: classify + xlsx download
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    const [xlsxUrl] = mockFetch.mock.calls[1] as [string];
    expect(xlsxUrl).toContain('/accounting/result/test-uuid-1234/xlsx');

    // tauriSave: defaultPath + filters 검증
    await waitFor(() => expect(tauriSave).toHaveBeenCalledOnce());
    expect(tauriSave).toHaveBeenCalledWith({
      defaultPath: 'butler_accounting_result.xlsx',
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    });

    // tauriWriteFile: 경로 + Uint8Array 검증
    await waitFor(() => expect(tauriWriteFile).toHaveBeenCalledOnce());
    const [writePath, writeData] = vi.mocked(tauriWriteFile).mock.calls[0];
    expect(writePath).toBe('/tmp/butler_accounting_result.xlsx');
    expect(writeData).toBeInstanceOf(Uint8Array);
  });

  it('test_download_cancel_does_not_write_file', async () => {
    // save dialog에서 사용자가 취소(null 반환) → writeFile 미호출
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) })
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) });
    vi.stubGlobal('fetch', mockFetch);

    vi.mocked(tauriSave).mockResolvedValueOnce(null);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 3000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    await waitFor(() => expect(tauriSave).toHaveBeenCalledOnce());
    expect(tauriWriteFile).not.toHaveBeenCalled();
  });

  it('test_phase_start_minimum_1500ms_display', async () => {
    // phase_start 직후 complete 도착해도 processing 상태가 1500ms 이상 표시됨을 검증
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

    vi.useFakeTimers();
    try {
      fireEvent.change(input);

      // 마이크로태스크 플러시: SSE 파싱 + MIN_PHASE_MS 타이머 등록
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 1500ms 이전: processing 상태 유지
      expect(screen.getByTestId('accounting-processing')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-result')).not.toBeInTheDocument();

      // 1500ms 경과 → MIN_PHASE_MS 타이머 해제 → done 상태 전환
      await vi.advanceTimersByTimeAsync(1500);
      for (let i = 0; i < 10; i++) await Promise.resolve();

      expect(screen.getByTestId('accounting-result')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-processing')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('test_download_fetch_failure_shows_error', async () => {
    // xlsx fetch 실패 시 error 상태 전환 검증
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) })
      .mockResolvedValueOnce({ ok: false, status: 404 });
    vi.stubGlobal('fetch', mockFetch);

    vi.mocked(tauriSave).mockResolvedValueOnce('/tmp/butler_result.xlsx');

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 3000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    await waitFor(() => expect(screen.getByTestId('accounting-error')).toBeInTheDocument());
    expect(screen.getByTestId('accounting-error').textContent).toContain('404');
    expect(tauriWriteFile).not.toHaveBeenCalled();
  });

  it('test_category_summary_shows_amount', async () => {
    // 계정과목별 건수 + 합계금액 표시 검증
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 3000 });

    const summary = screen.getByTestId('accounting-category-summary');
    expect(summary).toBeInTheDocument();
    // 급여 12,500,000원 표시 확인
    expect(summary.textContent).toContain('급여');
    expect(summary.textContent).toContain('12,500,000원');
    // 통신비 524,300원 표시 확인
    expect(summary.textContent).toContain('통신비');
    expect(summary.textContent).toContain('524,300원');
  });

  it('test_category_summary_hides_zero_amount', async () => {
    // total_amount=0일 때 합계금액 텍스트 미표시 검증
    const zeroAmountSummary = {
      total_rows: 5,
      classified_rows: 5,
      unclassified_rows: 0,
      categories: {
        '급여': { count: 3, avg_confidence: 0.90, total_amount: 0 },
        '통신비': { count: 2, avg_confidence: 0.85, total_amount: 0 },
      },
      avg_confidence: 0.88,
    };
    const eventsZero = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      {
        event: 'complete',
        data: {
          result_id: 'zero-uuid-0000',
          md_content: '## 보고서',
          summary: zeroAmountSummary,
          row_count: 5,
          category_count: 2,
        },
      },
    ];
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(eventsZero),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 3000 });

    const summary = screen.getByTestId('accounting-category-summary');
    expect(summary).toBeInTheDocument();
    // 카테고리 이름은 표시
    expect(summary.textContent).toContain('급여');
    // 합계금액은 미표시 (total_amount=0)
    expect(summary.textContent).not.toContain('합계');
    expect(summary.textContent).not.toContain('원');
  });
});
