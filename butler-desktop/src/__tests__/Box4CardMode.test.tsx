import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: async (command: string) =>
    command === 'get_sidecar_capability_token' ? 'test-capability-token' : undefined,
}));

function makeFetchMock() {
  return vi.fn().mockImplementation((url: string | URL | Request) => {
    if (String(url).includes('/health')) {
      return Promise.resolve(
        new Response(JSON.stringify({ status: 'ok', version: '0.9.0' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      );
    }
    const stream = new ReadableStream({ start(c) { c.close(); } });
    return Promise.resolve(new Response(stream, { status: 200 }));
  });
}

async function loadCardGrid(flag: '0' | '1' | undefined = undefined) {
  vi.resetModules();
  if (flag === undefined) {
    vi.unstubAllEnvs();
  } else {
    vi.stubEnv('VITE_BUTLER_BOX4_DOCUMENT_REVIEW', flag);
  }
  return import('../components/v1_1/CardGrid');
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('Box4 document_review feature flag (default ON)', () => {
  it('enables card 4 by default when the flag is missing', async () => {
    const { CardGrid, BOX4_DOCUMENT_REVIEW_ENABLED } = await loadCardGrid();
    const onCardSelect = vi.fn();

    render(<CardGrid onCardSelect={onCardSelect} />);

    expect(BOX4_DOCUMENT_REVIEW_ENABLED).toBe(true);
    const card4 = screen.getByTestId('card-4');
    expect(card4).not.toBeDisabled();
    fireEvent.click(card4);
    expect(onCardSelect).toHaveBeenCalledWith('document_review');
  });

  it('stays enabled when VITE_BUTLER_BOX4_DOCUMENT_REVIEW is 1', async () => {
    const { CardGrid, BOX4_DOCUMENT_REVIEW_ENABLED } = await loadCardGrid('1');
    const onCardSelect = vi.fn();

    render(<CardGrid onCardSelect={onCardSelect} />);

    expect(BOX4_DOCUMENT_REVIEW_ENABLED).toBe(true);
    const card4 = screen.getByTestId('card-4');
    expect(card4).not.toBeDisabled();
    fireEvent.click(card4);
    expect(onCardSelect).toHaveBeenCalledWith('document_review');
  });

  it('force-disables card 4 only when VITE_BUTLER_BOX4_DOCUMENT_REVIEW is 0 (kill switch)', async () => {
    const { CardGrid, BOX4_DOCUMENT_REVIEW_ENABLED } = await loadCardGrid('0');
    const onCardSelect = vi.fn();

    render(<CardGrid onCardSelect={onCardSelect} />);

    expect(BOX4_DOCUMENT_REVIEW_ENABLED).toBe(false);
    expect(screen.getByTestId('card-4')).toBeDisabled();
    fireEvent.click(screen.getByTestId('card-4'));
    expect(onCardSelect).not.toHaveBeenCalled();
  });

  it('sends document_review to the sidecar as numeric card_mode 4', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_BUTLER_BOX4_DOCUMENT_REVIEW', '1');
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);
    const { App, sidecarCardMode } = await import('../App');

    expect(sidecarCardMode('document_review')).toBe('4');
    expect(sidecarCardMode('attachment_edit')).toBe('4');

    render(<App />);

    fireEvent.click(screen.getByTestId('card-4'));
    fireEvent.change(screen.getByTestId('text-input'), {
      target: { value: '검토할 첨부 문서 초안입니다.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('send-btn'));
    });

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes('/api/analyze/stream')
      );
      expect(streamCall).toBeDefined();
      const body = (streamCall![1] as RequestInit).body as FormData;
      expect(body.get('card_mode')).toBe('4');
    });
  });
});
