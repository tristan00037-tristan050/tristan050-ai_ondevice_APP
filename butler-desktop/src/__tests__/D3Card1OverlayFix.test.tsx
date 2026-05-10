vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from '../App';
import { RequestParsingModal } from '../components/chat/RequestParsingModal';

const encoder = new TextEncoder();

function makeFetchMock() {
  return vi.fn().mockImplementation((url: string | URL | Request) => {
    if (String(url).includes('/api/precheck')) {
      return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
        headers: { 'Content-Type': 'application/json' },
      }));
    }
    const body = `event: complete\ndata: ${JSON.stringify({ result_text: '테스트' })}\n\n`;
    return Promise.resolve(new Response(
      new ReadableStream({ start(c) { c.enqueue(encoder.encode(body)); c.close(); } }),
      { status: 200 },
    ));
  });
}

const LONG_INPUT = '이번 주 금요일까지 계약서 검토 및 날인을 부탁드립니다. 확인 후 빠른 회신 부탁드립니다.';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('D-3 Card 1 Overlay Fix', () => {
  it('test_modal_overlay_separate_from_main', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const modal = screen.getByTestId('request-parsing-modal');

    // overlay must use position:fixed (inline style — not Tailwind, for Tauri WebView compat)
    expect(modal.style.position).toBe('fixed');
    // must cover full viewport from all edges
    expect(modal.style.top).toBe('0px');
    expect(modal.style.left).toBe('0px');
    expect(modal.style.bottom).toBe('0px');
    expect(modal.style.right).toBe('0px');
    // z-index must be high enough to cover all content
    expect(Number(modal.style.zIndex)).toBeGreaterThanOrEqual(999);
  });

  it('test_main_screen_not_compressed_when_modal_open', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(makeFetchMock());
    render(<App />);

    // Card grid must exist before opening modal
    expect(screen.getByTestId('card-grid')).toBeInTheDocument();

    // Open modal
    fireEvent.click(screen.getByTestId('card-1'));
    await waitFor(() => {
      expect(screen.getByTestId('request-parsing-modal')).toBeInTheDocument();
    });

    // Card grid must still be present
    expect(screen.getByTestId('card-grid')).toBeInTheDocument();

    // Card grid must NOT be a descendant of the modal (modal is overlay, not sidebar)
    const modal = screen.getByTestId('request-parsing-modal');
    const cardGrid = screen.getByTestId('card-grid');
    expect(modal.contains(cardGrid)).toBe(false);
  });

  it('test_textarea_min_15_rows', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const textarea = screen.getByRole('textbox');
    // rows={15} attribute ensures 15-line minimum
    expect(textarea.getAttribute('rows')).toBe('15');
    // inline style minHeight 400px for extra visual guarantee
    expect(textarea.style.minHeight).toBe('400px');
  });

  it('test_clipboard_button_is_primary_blue', () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const clipBtn = screen.getByTestId('clipboard-paste-btn');

    // Must have inline backgroundColor — primary blue (#2563eb = rgb(37,99,235))
    const bg = clipBtn.style.backgroundColor;
    expect(bg).toBeTruthy();
    // JSDOM may normalize hex to rgb or keep as hex
    const isBlue = bg === '#2563eb' || /rgb\(37,\s*99,\s*235\)/.test(bg);
    expect(isBlue).toBe(true);

    // Text must be white
    expect(clipBtn.style.color).toBe('white');
  });

  it('test_analyze_button_is_large_primary_full_width', async () => {
    render(<RequestParsingModal onClose={() => {}} />);
    const analyzeBtn = screen.getByRole('button', { name: '분석하기' });

    // Full-width via inline style
    expect(analyzeBtn.style.width).toBe('100%');

    // Initially disabled (no text → gray)
    expect(analyzeBtn).toBeDisabled();

    // Input sufficient text → button becomes enabled + blue
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: LONG_INPUT } });
    });

    expect(analyzeBtn).not.toBeDisabled();
    const bg = analyzeBtn.style.backgroundColor;
    const isBlue = bg === '#2563eb' || /rgb\(37,\s*99,\s*235\)/.test(bg);
    expect(isBlue).toBe(true);

    // Font size must be visually large (≥16px)
    const fs = parseInt(analyzeBtn.style.fontSize ?? '0', 10);
    expect(fs).toBeGreaterThanOrEqual(16);
  });
});
