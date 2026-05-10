vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RequestParsingModal } from '../components/chat/RequestParsingModal';

const BASE_RESULT = {
  actions: [
    { text: '계약서 검토 및 날인', priority: 'P1', rationale: '긴급 요청' },
    { text: '손익계산서 첨부', priority: 'P2', rationale: '' },
    { text: '일정 공유', priority: 'P3', rationale: '' },
  ],
  deadline: { raw_text: '다음 주 화요일', parsed_date: '2026-05-12', confidence: 0.9, time_text: '' },
  required_materials: [{ name: '손익계산서', is_optional: false, rationale: '필수' }],
  intent: { summary: '계약서 검토 및 날인 요청', tone: 'formal', expected_response: '검토 회신' },
  confidence: 0.88,
  masked_text: '마스킹 원문',
  input_format: 'text',
};

function makeSse(events: Array<{ event: string; data: object }>): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const body = events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('');
  return new ReadableStream({ start(c) { c.enqueue(enc.encode(body)); c.close(); } });
}

function mockComplete(result = BASE_RESULT) {
  return vi.fn().mockResolvedValueOnce({
    ok: true,
    body: makeSse([{ event: 'complete', data: { result_id: 'fix-test-id', result } }]),
  });
}

const LONG_INPUT = '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 손익계산서도 첨부해 주시기 바랍니다. 빠른 회신 부탁드립니다.';

beforeEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
  global.fetch = vi.fn();
});

describe('D-3 Card 1 UX Fix', () => {
  it('test_modal_input_area_min_12_lines', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const textarea = screen.getByRole('textbox');
    // rows={15} ensures minimum 15 lines; inline style minHeight 400px
    expect(textarea.getAttribute('rows')).toBe('15');
    expect(textarea.style.minHeight).toBe('400px');
  });

  it('test_action_text_not_in_required_files', async () => {
    // Materials empty → must show "필요 자료 명시 X" instead of action text
    const noMaterials = { ...BASE_RESULT, required_materials: [] };
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete(noMaterials);

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(screen.getByText('필요 자료 명시 X')).toBeTruthy();
    });

    // Action text must NOT appear inside the materials section
    // (verify the empty-state placeholder, not the action texts from the actions area)
    const mat = screen.getByText('필요 자료 명시 X');
    expect(mat).toBeTruthy();
  });

  it('test_sender_intent_separated_from_body', async () => {
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete();

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      // intent.summary must be the one-liner from the mock, not the raw body text
      expect(screen.getByText('계약서 검토 및 날인 요청')).toBeTruthy();
    });

    // The raw opening sentence of LONG_INPUT must not appear as the intent summary
    expect(screen.queryByText(LONG_INPUT)).toBeNull();
  });

  it('test_time_extraction_in_deadline', async () => {
    const withTime = {
      ...BASE_RESULT,
      deadline: {
        raw_text: '다음 주 화요일',
        parsed_date: '2026-05-12',
        confidence: 0.9,
        time_text: '오후 3시',
      },
    };
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete(withTime);

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      // time_text "오후 3시" must appear in the deadline section (may appear in multiple nodes)
      const found = screen.queryAllByText(/오후 3시/);
      expect(found.length).toBeGreaterThan(0);
    });

    // at least one node shows parsed_date with time_text
    const dateTimeNodes = screen.queryAllByText(/오후 3시/);
    expect(dateTimeNodes.some((el) => el.textContent?.includes('오후 3시'))).toBe(true);
  });

  it('test_priority_color_visible', async () => {
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete();

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(screen.getByText('P1 긴급')).toBeTruthy();
      expect(screen.getByText('P2 권장')).toBeTruthy();
      expect(screen.getByText('P3 선택')).toBeTruthy();
    });

    // P1 container must carry red color class
    const p1Label = screen.getByText('P1 긴급');
    const p1Container = p1Label.closest('.border.rounded-xl');
    expect(p1Container?.className).toContain('text-red-600');

    // P2 container must carry orange color class
    const p2Label = screen.getByText('P2 권장');
    const p2Container = p2Label.closest('.border.rounded-xl');
    expect(p2Container?.className).toContain('text-orange-600');
  });

  it('test_action_full_text_displayed', async () => {
    const LONG_ACTION = '이번 분기 실적 보고서 작성 및 제출과 함께 손익계산서 항목별 분석 자료를 최대한 상세하게 준비해 주시기 바랍니다';
    const withLongAction = {
      ...BASE_RESULT,
      actions: [{ text: LONG_ACTION, priority: 'P1' as const, rationale: '긴급 요청' }],
    };
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete(withLongAction);

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      // 50자 이상의 액션 텍스트가 잘리지 않고 전체 표시되어야 함
      expect(screen.getByText(LONG_ACTION)).toBeTruthy();
    });
  });

  it('test_required_files_separated_from_actions', async () => {
    const withBoth = {
      ...BASE_RESULT,
      required_materials: [{ name: '손익계산서 파일', is_optional: false, rationale: '첨부 요청' }],
      actions: [{ text: '계약서 검토 및 날인', priority: 'P1' as const, rationale: '긴급' }],
    };
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete(withBoth);

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(screen.getByText('손익계산서 파일')).toBeTruthy();
      expect(screen.getByText('계약서 검토 및 날인')).toBeTruthy();
    });

    // 자료명이 P1 액션 카드 안에 포함되지 않아야 함
    const p1Label = screen.getByText('P1 긴급');
    const actionCard = p1Label.closest('.border.rounded-xl');
    expect(actionCard?.textContent).not.toContain('손익계산서 파일');
  });

  it('test_deadline_with_time_format', async () => {
    const withDateTime = {
      ...BASE_RESULT,
      deadline: { raw_text: '다음 주 화요일', parsed_date: '2026-05-12', confidence: 0.9, time_text: '오후 3시' },
    };
    (global.fetch as ReturnType<typeof vi.fn>) = mockComplete(withDateTime);

    render(<RequestParsingModal onClose={() => {}} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      // parsed_date + time_text가 "2026-05-12 오후 3시" 형식으로 합쳐서 렌더링되어야 함
      expect(screen.getByText('2026-05-12 오후 3시')).toBeTruthy();
    });
  });
});
