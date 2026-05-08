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
    }, { timeout: 5000 });
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
    }, { timeout: 5000 });

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
    const xlsxBuffer = new ArrayBuffer(2048); // ≥ 1000 bytes to pass buffer guard
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

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

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
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => new ArrayBuffer(2048) }); // ≥ 1000 bytes
    vi.stubGlobal('fetch', mockFetch);

    vi.mocked(tauriSave).mockResolvedValueOnce(null);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    await waitFor(() => expect(tauriSave).toHaveBeenCalledOnce());
    expect(tauriWriteFile).not.toHaveBeenCalled();
  });

  it('test_phase_start_minimum_1500ms_display', async () => {
    // phase_start 직후 complete 도착해도 각 단계가 최소 1500ms씩 표시됨을 검증
    // inter-phase wait(1500ms) + complete MIN_PHASE_MS wait(1500ms) = 총 3000ms
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

      // 마이크로태스크 플러시: SSE 파싱 + inter-phase MIN_PHASE_MS 타이머 등록
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 1500ms 이전: 첫 번째 phase 표시 중, result 없음
      expect(screen.getByTestId('accounting-processing')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-result')).not.toBeInTheDocument();

      // 1500ms 경과 → inter-phase 타이머 해제 → 두 번째 phase_start 처리 → complete 타이머 등록
      await vi.advanceTimersByTimeAsync(1500);
      for (let i = 0; i < 10; i++) await Promise.resolve();
      // 아직 processing 상태 (complete MIN_PHASE_MS 타이머 대기 중)
      expect(screen.getByTestId('accounting-processing')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-result')).not.toBeInTheDocument();

      // 추가 1500ms 경과 → complete MIN_PHASE_MS 타이머 해제 → done 전환
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

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

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

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

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

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    const summary = screen.getByTestId('accounting-category-summary');
    expect(summary).toBeInTheDocument();
    // 카테고리 이름은 표시
    expect(summary.textContent).toContain('급여');
    // 합계금액 컬럼 미표시 (total_amount=0 → hasAmt=false)
    expect(summary.textContent).not.toContain('합계금액');
    expect(summary.textContent).not.toContain('원');
  });

  it('test_category_amount_negative_preserves_sign', async () => {
    // 음수 total_amount → "-xxx,xxx원" 부호 포함 표시 (Math.abs 제거 검증)
    const negSummary = {
      total_rows: 3,
      classified_rows: 3,
      unclassified_rows: 0,
      categories: {
        '직원급여': { count: 2, avg_confidence: 0.90, total_amount: -6000000 },
        '통신비':  { count: 1, avg_confidence: 0.85, total_amount: -88000 },
      },
      avg_confidence: 0.88,
    };
    const eventsNeg = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      {
        event: 'complete',
        data: {
          result_id: 'neg-uuid-0001',
          md_content: '## 보고서',
          summary: negSummary,
          row_count: 3,
          category_count: 2,
        },
      },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(eventsNeg),
    }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    const summaryEl = screen.getByTestId('accounting-category-summary');
    // 음수 부호(-) 포함 표시
    expect(summaryEl.textContent).toContain('-');
    // 6,000,000원 숫자 포함
    expect(summaryEl.textContent).toContain('6,000,000원');
  });

  it('test_category_amount_positive_no_sign', async () => {
    // 양수 total_amount → "xxx,xxx원" 형식 (마이너스 없음)
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: makeSseStream(SSE_EVENTS_OK),  // MOCK_SUMMARY: 급여 12,500,000 / 통신비 524,300 (모두 양수)
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    const summaryEl = screen.getByTestId('accounting-category-summary');
    // 양수: 마이너스 없이 표시
    expect(summaryEl.textContent).toContain('12,500,000원');
    expect(summaryEl.textContent).not.toMatch(/-12,500,000원/);
    expect(summaryEl.textContent).toContain('524,300원');
  });

  // A.3 — 표 형식 테스트 (4개)

  it('test_category_table_renders_with_headers', async () => {
    // accounting-category-table이 thead 헤더 4종을 렌더해야 한다
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-category-table')).toBeInTheDocument(), { timeout: 5000 });
    const table = screen.getByTestId('accounting-category-table');
    expect(table.textContent).toContain('분류과목');
    expect(table.textContent).toContain('건수');
    expect(table.textContent).toContain('합계금액');
    expect(table.textContent).toContain('비율');
  });

  it('test_category_table_negative_amount_has_debit_color', async () => {
    // 음수 합계금액 td 셀에 --color-accounting-debit 색상이 인라인 스타일로 적용되어야 한다
    const negSummary = {
      total_rows: 1,
      classified_rows: 1,
      unclassified_rows: 0,
      categories: { '직원급여': { count: 1, avg_confidence: 0.90, total_amount: -6000000 } },
      avg_confidence: 0.90,
    };
    const eventsNeg = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      { event: 'complete', data: { result_id: 'neg-color', md_content: '## 보고서', summary: negSummary, row_count: 1, category_count: 1 } },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsNeg) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-category-table')).toBeInTheDocument(), { timeout: 5000 });
    const table = screen.getByTestId('accounting-category-table');
    const allCells = Array.from(table.querySelectorAll('td'));
    const debitCells = allCells.filter(td => td.style.color === 'var(--color-accounting-debit)');
    expect(debitCells.length).toBeGreaterThan(0);
  });

  it('test_category_table_totals_row_present', async () => {
    // tfoot 합계행에 전체 건수 합계와 100% 비율이 표시되어야 한다
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-category-table')).toBeInTheDocument(), { timeout: 5000 });
    const table = screen.getByTestId('accounting-category-table');
    const tfoot = table.querySelector('tfoot');
    expect(tfoot).not.toBeNull();
    expect(tfoot!.textContent).toContain('합계');
    expect(tfoot!.textContent).toContain('100%');
    // MOCK_SUMMARY: 급여 5건 + 통신비 4건 = 9건
    expect(tfoot!.textContent).toContain('9건');
  });

  it('test_category_table_zero_amount_hides_column', async () => {
    // 모든 total_amount=0일 때 합계금액 헤더/컬럼이 렌더되지 않아야 한다
    const zeroSummary = {
      total_rows: 2,
      classified_rows: 2,
      unclassified_rows: 0,
      categories: { '기타': { count: 2, avg_confidence: 0.80, total_amount: 0 } },
      avg_confidence: 0.80,
    };
    const eventsZero = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      { event: 'complete', data: { result_id: 'zero-col', md_content: '## 보고서', summary: zeroSummary, row_count: 2, category_count: 1 } },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsZero) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-category-table')).toBeInTheDocument(), { timeout: 5000 });
    const table = screen.getByTestId('accounting-category-table');
    expect(table.textContent).not.toContain('합계금액');
    expect(table.textContent).not.toContain('원');
  });

  // C.3 — SSE phase 메시지 타이밍 테스트 (2개)

  it('test_first_phase_message_shown_before_timer', async () => {
    // 첫 번째 phase_start 메시지는 타이머 없이 즉시 UI에 반영되어야 한다
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    vi.useFakeTimers();
    try {
      fireEvent.change(input);
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 타이머 진행 없이 첫 번째 phase 메시지가 이미 표시되어야 함
      const processingEl = screen.getByTestId('accounting-processing');
      expect(processingEl.textContent).toContain('분류 중');
    } finally {
      vi.useRealTimers();
    }
  });

  it('test_second_phase_message_shown_after_timer', async () => {
    // 두 번째 phase_start 메시지는 MIN_PHASE_MS(1500ms) 경과 후 전환되어야 한다
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    vi.useFakeTimers();
    try {
      fireEvent.change(input);
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 1500ms 이전: 첫 번째 phase '분류 중' 표시 중
      expect(screen.getByTestId('accounting-processing').textContent).toContain('분류 중');
      expect(screen.getByTestId('accounting-processing').textContent).not.toContain('보고서');

      // 1500ms 경과 → inter-phase 타이머 해제 → 두 번째 phase '보고서 생성 중' 전환
      await vi.advanceTimersByTimeAsync(1500);
      for (let i = 0; i < 10; i++) await Promise.resolve();

      expect(screen.getByTestId('accounting-processing').textContent).toContain('보고서');
    } finally {
      vi.useRealTimers();
    }
  });

  // Cancellation safety tests (codex P1)

  it('test_abort_during_inter_phase_delay_prevents_stale_update', async () => {
    // inter-phase delay 도중 abort 시 phase_2 setPhase가 호출되지 않아야 한다 (Promise.race 즉시 취소)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(SSE_EVENTS_OK) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    vi.useFakeTimers();
    try {
      fireEvent.change(input);
      for (let i = 0; i < 30; i++) await Promise.resolve();

      // 첫 번째 phase 표시 중, inter-phase delay(1500ms) 대기 중
      expect(screen.getByTestId('accounting-processing').textContent).toContain('분류 중');

      // 파일 삭제 버튼 클릭 → abort + setPhase(idle) (1500ms 타이머 만료 전)
      fireEvent.click(screen.getByTestId('accounting-file-delete-btn'));
      for (let i = 0; i < 10; i++) await Promise.resolve();

      // 즉시 idle 전환 — abort race가 timeout race보다 먼저 종료됨
      expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-processing')).not.toBeInTheDocument();

      // 1500ms 경과 후에도 여전히 idle (phase_2 setPhase 미호출)
      await vi.advanceTimersByTimeAsync(1500);
      for (let i = 0; i < 10; i++) await Promise.resolve();

      expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
      expect(screen.queryByTestId('accounting-processing')).not.toBeInTheDocument();
      expect(screen.queryByTestId('accounting-result')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('test_stale_phase_start_after_abort_does_not_change_state', async () => {
    // abort 후 늦게 도착하는 phase_start 이벤트가 state를 변경하지 않아야 한다
    const encoder = new TextEncoder();
    let enqueue!: (chunk: Uint8Array) => void;
    let closeStream!: () => void;
    const delayedStream = new ReadableStream<Uint8Array>({
      start(c) {
        enqueue = (chunk) => c.enqueue(chunk);
        closeStream = () => c.close();
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: delayedStream }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    // 첫 번째 phase_start 도착
    act(() => { enqueue(encoder.encode('event: phase_start\ndata: {"status_message":"분류 중 — 회계과목 매칭"}\n\n')); });
    await waitFor(() => expect(screen.getByTestId('accounting-processing')).toBeInTheDocument());

    // abort: 삭제 버튼 → abortRef.abort() + setPhase(idle)
    fireEvent.click(screen.getByTestId('accounting-file-delete-btn'));
    for (let i = 0; i < 10; i++) await Promise.resolve();
    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();

    // stale 이벤트 도착 (abort 이후) — while 루프 상단 ctrl.signal.aborted 체크로 무시되어야 함
    act(() => { enqueue(encoder.encode('event: phase_start\ndata: {"status_message":"보고서 생성 중 — 요약 집계"}\n\n')); });
    for (let i = 0; i < 10; i++) await Promise.resolve();

    // idle 상태 유지
    expect(screen.getByTestId('accounting-drop-zone')).toBeInTheDocument();
    expect(screen.queryByTestId('accounting-processing')).not.toBeInTheDocument();

    act(() => { closeStream(); });
  });

  // A.4 — 다운로드 버퍼 정확성 테스트

  it('test_download_buffer_passed_exactly_to_writefile', async () => {
    // fetch arrayBuffer 바이트가 tauriWriteFile에 그대로 전달되어야 한다 (byte-level 비교)
    const xlsx = new Uint8Array(2048);
    xlsx[0] = 0x50; xlsx[1] = 0x4B; xlsx[2] = 0x03; xlsx[3] = 0x04; // ZIP magic
    for (let i = 4; i < 2048; i++) xlsx[i] = (i % 256);
    const xlsxBuffer = xlsx.buffer;

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) })
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => xlsxBuffer });
    vi.stubGlobal('fetch', mockFetch);
    vi.mocked(tauriSave).mockResolvedValueOnce('/tmp/out.xlsx');
    vi.mocked(tauriWriteFile).mockResolvedValueOnce(undefined);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    await waitFor(() => expect(tauriWriteFile).toHaveBeenCalledOnce());
    const [, writeData] = vi.mocked(tauriWriteFile).mock.calls[0];
    expect(writeData).toBeInstanceOf(Uint8Array);
    const written = writeData as Uint8Array;
    expect(written.byteLength).toBe(2048);
    expect(written[0]).toBe(0x50);
    expect(written[1]).toBe(0x4B);
    // sample bytes across the buffer
    for (let i = 4; i < 2048; i += 128) {
      expect(written[i]).toBe(i % 256);
    }
  });

  it('test_download_small_buffer_shows_error_no_writefile', async () => {
    // 응답 바이트가 1000 미만이면 에러 상태로 전환하고 writeFile을 호출하지 않아야 한다
    const tinyBuffer = new ArrayBuffer(42); // < 1000

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, body: makeSseStream(SSE_EVENTS_OK) })
      .mockResolvedValueOnce({ ok: true, arrayBuffer: async () => tinyBuffer });
    vi.stubGlobal('fetch', mockFetch);

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    await act(async () => {
      fireEvent.click(screen.getByTestId('accounting-download-btn'));
    });

    await waitFor(() => expect(screen.getByTestId('accounting-error')).toBeInTheDocument());
    expect(screen.getByTestId('accounting-error').textContent).toContain('42B');
    expect(tauriWriteFile).not.toHaveBeenCalled();
  });

  // B.3 — ReactMarkdown 보고서 음수 금액 debit 색상 테스트

  it('test_report_markdown_td_debit_color_for_negative_amount', async () => {
    // 보고서(ReactMarkdown) 테이블 td에서 음수 금액 셀에 --color-accounting-debit 색상이 적용되어야 한다
    const mdWithNegative = [
      '## 보고서\n',
      '| 계정과목 | 건수 | 합계금액 |',
      '|---------|------|---------|',
      '| 급여 | 3 | 3,000,000원 |',
      '| 광고비 | 2 | -500,000원 |',
    ].join('\n');

    const eventsWithMd = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      {
        event: 'complete',
        data: {
          result_id: 'md-debit-test',
          md_content: mdWithNegative,
          summary: MOCK_SUMMARY,
          row_count: 5,
          category_count: 2,
        },
      },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsWithMd) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });

    // 보고서 열기
    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    await waitFor(() => expect(screen.getByTestId('accounting-report-content')).toBeInTheDocument());

    const reportEl = screen.getByTestId('accounting-report-content');
    const allTds = Array.from(reportEl.querySelectorAll('td'));
    const debitTds = allTds.filter(td => td.style.color === 'var(--color-accounting-debit)');
    expect(debitTds.length).toBeGreaterThan(0);
    const debitText = debitTds.map(td => td.textContent).join('');
    expect(debitText).toContain('-500,000원');
  });

  // C.2 — 결과 테이블 양수 카테고리 먼저 정렬 테스트

  it('test_result_table_positive_categories_before_negative', async () => {
    // 결과 테이블에서 양수 합계금액 카테고리가 음수보다 앞에 위치해야 한다
    const mixedSummary = {
      total_rows: 6,
      classified_rows: 6,
      unclassified_rows: 0,
      categories: {
        '광고선전비': { count: 2, avg_confidence: 0.88, total_amount: -400000 },
        '매출액': { count: 3, avg_confidence: 0.95, total_amount: 9000000 },
        '통신비': { count: 1, avg_confidence: 0.82, total_amount: -88000 },
      },
      avg_confidence: 0.90,
    };
    const eventsMixed = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      { event: 'complete', data: { result_id: 'sort-test', md_content: '## 보고서', summary: mixedSummary, row_count: 6, category_count: 3 } },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsMixed) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-category-table')).toBeInTheDocument(), { timeout: 5000 });
    const table = screen.getByTestId('accounting-category-table');
    const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
    expect(bodyRows.length).toBe(3);

    // 첫 번째 행: 양수 카테고리 (매출액)
    expect(bodyRows[0].textContent).toContain('매출액');
    // 두 번째, 세 번째 행: 음수 카테고리
    expect(bodyRows[1].textContent).toMatch(/광고선전비|통신비/);
    expect(bodyRows[2].textContent).toMatch(/광고선전비|통신비/);

    // 두 음수 카테고리 중 절댓값 큰 것(광고선전비 400000)이 먼저
    expect(bodyRows[1].textContent).toContain('광고선전비');
    expect(bodyRows[2].textContent).toContain('통신비');
  });

  // A.1 — ReactMarkdown 보고서 table CSS 스타일 검증 (PR #692)

  it('test_report_table_has_collapse_border_style', async () => {
    // 보고서 ReactMarkdown 표에 borderCollapse: collapse 스타일이 적용되어야 한다
    const mdWithTable = [
      '## 보고서',
      '',
      '| 계정과목 | 건수 | 합계금액 |',
      '|---------|------|---------|',
      '| 급여 | 3 | 3,000,000원 |',
    ].join('\n');

    const eventsWithTable = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      {
        event: 'complete',
        data: {
          result_id: 'table-style-test',
          md_content: mdWithTable,
          summary: MOCK_SUMMARY,
          row_count: 3,
          category_count: 1,
        },
      },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsWithTable) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    await waitFor(() => expect(screen.getByTestId('accounting-report-content')).toBeInTheDocument());

    const reportEl = screen.getByTestId('accounting-report-content');
    const tableEl = reportEl.querySelector('table');
    expect(tableEl).not.toBeNull();
    expect(tableEl!.style.borderCollapse).toBe('collapse');
    expect(tableEl!.style.width).toBe('100%');
  });

  it('test_report_th_has_padding_style', async () => {
    // 보고서 ReactMarkdown 표 th 헤더 셀에 padding 스타일이 적용되어야 한다
    const mdWithTable = [
      '## 보고서',
      '',
      '| 계정과목 | 건수 |',
      '|---------|------|',
      '| 급여 | 5 |',
    ].join('\n');

    const eventsWithTable = [
      { event: 'phase_start', data: { status_message: '분류 중 — 회계과목 매칭' } },
      { event: 'phase_start', data: { status_message: '보고서 생성 중 — 요약 집계' } },
      {
        event: 'complete',
        data: {
          result_id: 'th-style-test',
          md_content: mdWithTable,
          summary: MOCK_SUMMARY,
          row_count: 5,
          category_count: 1,
        },
      },
    ];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: makeSseStream(eventsWithTable) }));

    render(<AccountingModal onClose={() => {}} />);
    const input = screen.getByTestId('accounting-file-input') as HTMLInputElement;
    const file = new File(['col\nval'], 'data.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => expect(screen.getByTestId('accounting-result')).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByTestId('accounting-report-toggle'));
    await waitFor(() => expect(screen.getByTestId('accounting-report-content')).toBeInTheDocument());

    const reportEl = screen.getByTestId('accounting-report-content');
    const thEls = Array.from(reportEl.querySelectorAll('th'));
    expect(thEls.length).toBeGreaterThan(0);
    // 모든 th에 padding 스타일 적용 확인
    thEls.forEach(th => {
      expect(th.style.padding).toBeTruthy();
      expect(th.style.fontWeight).toBe('600');
    });
  });
});
