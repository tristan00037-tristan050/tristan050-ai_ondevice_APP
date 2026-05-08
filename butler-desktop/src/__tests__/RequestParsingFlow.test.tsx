vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RequestParsingModal } from '../components/chat/RequestParsingModal';

const MOCK_RESULT = {
  actions: [
    { text: '계약서 검토 및 날인', priority: 'P1', rationale: '긴급 요청' },
    { text: '손익계산서 첨부', priority: 'P2', rationale: '' },
  ],
  deadline: { raw_text: '다음 주 화요일', parsed_date: '2026-05-12', confidence: 0.9 },
  required_materials: [
    { name: '손익계산서', is_optional: false, rationale: '필수' },
  ],
  intent: { summary: '계약서 검토 요청', tone: 'formal', expected_response: '검토 회신' },
  confidence: 0.88,
  masked_text: '마스킹 처리된 원문',
  input_format: 'text',
};

function makeSseStream(events: Array<{ event: string; data: object }>): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const body = events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('');
  return new ReadableStream({
    start(ctrl) {
      ctrl.enqueue(encoder.encode(body));
      ctrl.close();
    },
  });
}

const SSE_OK = [
  { event: 'phase_start', data: { phase: 1, status_message: 'PII 마스킹 중' } },
  { event: 'phase_start', data: { phase: 2, status_message: '날짜·액션 추출 중' } },
  { event: 'phase_start', data: { phase: 3, status_message: '의도 분석 중' } },
  { event: 'phase_start', data: { phase: 4, status_message: '결과 저장 중' } },
  { event: 'complete', data: { result_id: 'test-id-001', result: MOCK_RESULT } },
];

describe('RequestParsingModal', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.unstubAllGlobals();
    global.fetch = vi.fn();
  });

  it('분석하기 버튼은 30자 미만 텍스트에서 비활성화', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const btn = screen.getByRole('button', { name: '분석하기' });
    expect(btn).toBeDisabled();
  });

  it('텍스트 입력 후 분석하기 버튼 활성화', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 회신 부탁드립니다.' } });
    const btn = screen.getByRole('button', { name: '분석하기' });
    expect(btn).not.toBeDisabled();
  });

  it('SSE complete 이벤트 후 결과 렌더링', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      body: makeSseStream(SSE_OK),
    });

    render(<RequestParsingModal onClose={() => {}} />);
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 빠른 회신 부탁드립니다.' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(screen.getByText('계약서 검토 및 날인')).toBeTruthy();
    });
    expect(screen.getByText('계약서 검토 요청')).toBeTruthy();
    expect(screen.getByText('다음 주 화요일')).toBeTruthy();
  });

  it('P1 액션은 빨간 badge로 표시', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      body: makeSseStream(SSE_OK),
    });

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 빠른 회신 부탁드립니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => screen.getByText(/P1/));
    const p1Badge = screen.getByText(/P1 긴급/);
    expect(p1Badge).toBeTruthy();
  });

  it('.txt 파일 → FileReader.readAsText로 textarea에 삽입 (fetch 호출 없음)', async () => {
    const TXT_CONTENT = '안녕하세요. 다음 주 화요일까지 보고서를 제출해 주시면 감사하겠습니다.';
    class MockFileReader {
      result: string | null = null;
      onload: (() => void) | null = null;
      readAsText(_file: File, _enc?: string) {
        this.result = TXT_CONTENT;
        this.onload?.();
      }
    }
    vi.stubGlobal('FileReader', MockFileReader);

    render(<RequestParsingModal onClose={() => {}} />);

    const file = new File([TXT_CONTENT], 'report.txt', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    await act(async () => {
      fireEvent.change(input);
    });

    await waitFor(() => {
      expect(screen.getByRole('textbox')).toHaveValue(TXT_CONTENT);
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('.docx 파일 → /request_parsing/parse_file_stream으로 multipart POST', async () => {
    const SSE_DOCX = [
      { event: 'phase_start', data: { phase: 1, status_message: '파일 텍스트 추출 중' } },
      { event: 'complete', data: { result_id: 'docx-id-001', result: MOCK_RESULT } },
    ];
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      body: makeSseStream(SSE_DOCX),
    });

    render(<RequestParsingModal onClose={() => {}} />);

    const file = new File([new ArrayBuffer(8)], 'contract.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    await act(async () => {
      fireEvent.change(input);
    });

    await waitFor(() => {
      expect((global.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
    });
    const [url, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url as string).toContain('/request_parsing/parse_file_stream');
    expect((opts as RequestInit).method).toBe('POST');
    expect((opts as RequestInit).body).toBeInstanceOf(FormData);
  });

  it('서버 오류 시 오류 화면 표시', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: '파싱 오류 발생' }),
    });

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 빠른 회신 부탁드립니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(screen.getByText('파싱 오류 발생')).toBeTruthy();
    });
  });
});
