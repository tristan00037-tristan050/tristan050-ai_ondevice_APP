import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: async (command: string) =>
    command === 'get_sidecar_capability_token' ? 'test-capability-token' : undefined,
}));

import { App, sidecarCardMode } from '../App';
import { CardGrid } from '../components/v1_1/CardGrid';

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

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('Box4 card mode mapping', () => {
  it('maps frontend modes to sidecar card ids', () => {
    expect(sidecarCardMode('attachment_edit')).toBe('4');
    expect(sidecarCardMode('free')).toBe('free');
    expect(sidecarCardMode('unknown_mode')).toBe('free');
  });

  it('enables card 4 in the v1.1 card grid', () => {
    const onCardSelect = vi.fn();
    render(<CardGrid onCardSelect={onCardSelect} />);

    const card4 = screen.getByTestId('card-4');
    expect(card4).not.toBeDisabled();

    fireEvent.click(card4);
    expect(onCardSelect).toHaveBeenCalledWith('attachment_edit');
  });

  it('sends attachment_edit to the sidecar as numeric card_mode 4', async () => {
    const fetchMock = makeFetchMock();
    vi.spyOn(global, 'fetch').mockImplementation(fetchMock);

    render(<App />);

    fireEvent.click(screen.getByTestId('card-4'));
    fireEvent.change(screen.getByTestId('text-input'), {
      target: { value: '수정할 첨부 문서 초안입니다.' },
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
