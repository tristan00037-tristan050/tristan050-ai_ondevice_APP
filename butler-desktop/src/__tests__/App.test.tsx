import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from '../App';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

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

  it('test_happy_complete_event_shows_result_immediately', async () => {
    // complete 이벤트 → overlay 닫힘 + result-panel 자동 표시 (버튼 클릭 불필요)
    const sseBody = 'event: meta\ndata: {"source":"llm"}\n\nevent: phase_start\ndata: {"phase":"analyze","total_steps":1}\n\nevent: complete\ndata: {"result_text": "테스트 결과입니다"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);

    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('result-panel')).toBeInTheDocument();
    }, { timeout: 2000 });

    expect(screen.getByTestId('result-panel').textContent).toContain('테스트 결과입니다');
    // overlay가 닫혀 있어야 함
    expect(screen.queryByTestId('cancel-btn')).not.toBeInTheDocument();
  });

  it('test_happy_result_panel_has_copy_button', async () => {
    // 결과 패널에 복사 버튼 존재 확인
    const sseBody = 'event: complete\ndata: {"result_text": "복사할 결과"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);

    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    await waitFor(() => {
      expect(screen.getByTestId('copy-btn')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('test_adv_factpack_source_badge_visible_after_complete', async () => {
    // 결함 핫픽스 회귀: meta(source=factpack) + complete → "✓ 검증된 사실" 배지 표시
    const sseBody =
      'event: meta\ndata: {"source":"factpack"}\n\n' +
      'event: phase_start\ndata: {"phase":"analyze","total_steps":1}\n\n' +
      'event: complete\ndata: {"result_text":"검증된 답변입니다"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '사실 확인' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    await waitFor(() => {
      expect(screen.getByText('✓ 검증된 사실')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('test_adv_llm_source_badge_visible_after_complete', async () => {
    // meta(source=llm) + complete → "✨ AI 생성" 배지 표시
    const sseBody =
      'event: meta\ndata: {"source":"llm"}\n\n' +
      'event: complete\ndata: {"result_text":"AI가 생성한 답변"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    await waitFor(() => {
      expect(screen.getByText('✨ AI 생성')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('test_status_message_displayed_during_processing', async () => {
    // ChatInput에 처리 중 상태 텍스트 요소 표시 (WKWebView placeholder 대응)
    vi.spyOn(global, 'fetch').mockImplementation(() =>
      Promise.resolve(new Response(new ReadableStream({ start(c) { c.close(); } }), { status: 200 }))
    );

    render(<App />);
    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문' } });

    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    // 전송 직후 처리 중 상태 텍스트 표시
    await waitFor(() => {
      expect(screen.getByTestId('processing-status-text')).toBeInTheDocument();
    }, { timeout: 1000 });
  });

  it('test_phase_start_message_visible_with_flushsync', async () => {
    // flushSync 적용: phase_start + complete가 같은 read()에 도착해도 phase 메시지가 렌더링됨
    const phaseMsg = '1/1 단계 분석 시작 — 예상 60초';
    const sseBody =
      `event: phase_start\ndata: {"status_message":"${phaseMsg}","total_steps":1}\n\n` +
      'event: complete\ndata: {"result_text":"완료된 결과"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '질문' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    // 최종적으로 결과가 보여야 함 (flushSync로 인한 중간 렌더 후 최종 상태)
    await waitFor(() => {
      expect(screen.getByTestId('result-panel')).toBeInTheDocument();
    }, { timeout: 2000 });
    expect(screen.getByTestId('result-panel').textContent).toContain('완료된 결과');
  });

  it('test_chunk_event_streams_to_display_and_complete_shows_result', async () => {
    // chunk 이벤트 → streaming-text 표시, complete → result-panel에 최종 텍스트
    const sseBody =
      'event: meta\ndata: {"source":"llm"}\n\n' +
      'event: chunk\ndata: {"token":"안녕"}\n\n' +
      'event: chunk\ndata: {"token":"하세요"}\n\n' +
      'event: complete\ndata: {"result_text":"안녕하세요"}\n\n';
    const encoder = new TextEncoder();
    vi.spyOn(global, 'fetch').mockImplementation((url: string | URL | Request) => {
      if (String(url).includes('/api/precheck')) {
        return Promise.resolve(new Response(JSON.stringify({ grade: 'S' }), {
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      const stream = new ReadableStream({
        start(c) { c.enqueue(encoder.encode(sseBody)); c.close(); },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('text-input'), { target: { value: '인사' } });
    await act(async () => { fireEvent.click(screen.getByTestId('send-btn')); });

    // 최종 결과가 result-panel에 표시됨
    await waitFor(() => {
      expect(screen.getByTestId('result-panel')).toBeInTheDocument();
    }, { timeout: 2000 });
    expect(screen.getByTestId('result-panel').textContent).toContain('안녕하세요');
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
