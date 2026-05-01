import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from '../App';

afterEach(() => vi.restoreAllMocks());

function makeFetchMock() {
  return vi.fn().mockImplementation((url: string | URL | Request) => {
    if (String(url).includes('/api/precheck')) {
      return Promise.resolve(
        new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      );
    }
    // /api/analyze/stream: return empty stream so reader returns done immediately
    const stream = new ReadableStream({ start(c) { c.close(); } });
    return Promise.resolve(new Response(stream, { status: 200 }));
  });
}

describe('App integration', () => {
  it('test_adv_attached_files_sent_to_backend', async () => {
    // P1 회귀: 첨부 파일이 /api/analyze/stream 요청의 FormData에 포함돼야 한다
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);

    const { container } = render(<App />);

    // 파일 첨부 (hidden file input 직접 조작)
    const file = new File(['통장내용'], 'bank.pdf', { type: 'application/pdf' });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });

    await act(async () => {
      fireEvent.change(fileInput);
    });

    // precheck가 끝나면 file-list 나타남
    await waitFor(() => {
      expect(screen.getByTestId('file-list')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('text-input'), {
      target: { value: '회계 분류해줘' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('send-btn'));
    });

    // 핵심: /api/analyze/stream 요청 body가 FormData이고 file_0 포함
    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes('/api/analyze/stream')
      );
      expect(streamCall).toBeDefined();
      const body = streamCall![1].body as FormData;
      expect(body.has('file_0')).toBe(true);
      expect((body.get('file_0') as File).name).toBe('bank.pdf');
    });
  });

  it('test_adv_homescreen_submit_button_triggers_handler', async () => {
    // P2 회귀: 전송 버튼 클릭 → fetch 실제 호출 (no-op 아님)
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);

    render(<App />);

    fireEvent.change(screen.getByTestId('text-input'), {
      target: { value: 'test query' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('send-btn'));
    });

    await waitFor(
      () => {
        const streamCalls = fetchMock.mock.calls.filter(([url]) =>
          String(url).includes('/api/analyze/stream')
        );
        expect(streamCalls.length).toBeGreaterThan(0);
      },
      { timeout: 1000 }
    );
  });

  it('test_happy_no_files_works_with_text_only', async () => {
    // 정상 흐름: 파일 없이 텍스트만 전송 → query 포함, file_0 없음
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);

    render(<App />);

    fireEvent.change(screen.getByTestId('text-input'), {
      target: { value: '회의록 정리' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('send-btn'));
    });

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes('/api/analyze/stream')
      );
      expect(streamCall).toBeDefined();
      const body = streamCall![1].body as FormData;
      expect(body.get('query')).toBe('회의록 정리');
      expect(body.has('file_0')).toBe(false);
    });
  });
});
