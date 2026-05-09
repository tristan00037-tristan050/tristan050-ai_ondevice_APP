vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from '../App';
import { EmptyState } from '../components/chat/EmptyState';
import { RequestParsingModal } from '../components/chat/RequestParsingModal';

const encoder = new TextEncoder();

function makeCompleteStream(resultText = '테스트 결과') {
  const body = `event: complete\ndata: ${JSON.stringify({ result_text: resultText })}\n\n`;
  return new ReadableStream<Uint8Array>({
    start(c) { c.enqueue(encoder.encode(body)); c.close(); },
  });
}

function makeFetchMock() {
  return vi.fn().mockImplementation((url: string | URL | Request) => {
    if (String(url).includes('/api/precheck')) {
      return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    return Promise.resolve(new Response(makeCompleteStream(), { status: 200 }));
  });
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('D-3 Card 1 통합', () => {
  it('test_main_screen_shows_8_cards_with_lucide_icons', () => {
    // 8개 카드 표시 + Lucide SVG 아이콘 + 비활성 카드 disabled
    const { container } = render(<EmptyState />);
    for (let i = 1; i <= 8; i++) {
      expect(screen.getByTestId(`card-${i}`)).toBeInTheDocument();
    }
    // Cards 1 and 5 are active; 2,3,4,6,7,8 are disabled
    expect(screen.getByTestId('card-1')).not.toBeDisabled();
    expect(screen.getByTestId('card-5')).not.toBeDisabled();
    for (const id of [2, 3, 4, 6, 7, 8]) {
      expect(screen.getByTestId(`card-${id}`)).toBeDisabled();
    }
    // Lucide renders SVG elements
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThanOrEqual(8);
  });

  it('test_card1_click_opens_modal', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(makeFetchMock());
    render(<App />);

    const card1 = screen.getByTestId('card-1');
    expect(card1).not.toBeDisabled();

    fireEvent.click(card1);

    await waitFor(() => {
      expect(screen.getByTestId('request-parsing-modal')).toBeInTheDocument();
    });
  });

  it('test_modal_routes_to_request_parsing_endpoint', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream({ start(c) { c.close(); } }),
    });
    vi.spyOn(global, 'fetch').mockImplementation(fetchSpy);

    render(<RequestParsingModal onClose={() => {}} />);

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 회신 부탁드립니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분석하기' }));
    });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const calledUrl = String(fetchSpy.mock.calls[0][0]);
    expect(calledUrl).toContain('/request_parsing/parse_stream');
  });

  it('test_chat_fallback_blocked', async () => {
    const fetchSpy = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchSpy);
    render(<App />);

    // Open RequestParsingModal via card 1
    fireEvent.click(screen.getByTestId('card-1'));
    await waitFor(() => {
      expect(screen.getByTestId('request-parsing-modal')).toBeInTheDocument();
    });

    // Modal opened — general chat should NOT have been called
    const analyzeCalls = fetchSpy.mock.calls.filter(([url]) =>
      String(url).includes('/api/analyze/stream')
    );
    expect(analyzeCalls.length).toBe(0);
  });

  it('test_card_area_persists_after_question', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(makeFetchMock());
    render(<App />);

    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문입니다' } });
    await act(async () => {
      fireEvent.click(screen.getByTestId('send-btn'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('result-panel')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Compact card strip still rendered above MessageList
    expect(screen.getByTestId('card-grid')).toBeInTheDocument();
  });

  it('test_no_emoji_in_ui', () => {
    const emojiRe = /[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}]/u;

    const { unmount: u1 } = render(<EmptyState />);
    expect(emojiRe.test(document.body.textContent ?? '')).toBe(false);
    u1();

    render(<RequestParsingModal onClose={() => {}} />);
    expect(emojiRe.test(document.body.textContent ?? '')).toBe(false);
  });
});
