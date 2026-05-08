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
