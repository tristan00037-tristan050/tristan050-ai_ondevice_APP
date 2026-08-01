import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/sidecarFetch', async importOriginal => ({
  ...await importOriginal<typeof import('../../lib/sidecarFetch')>(),
  sidecarFetch: vi.fn(),
}));

import { sidecarFetch } from '../../lib/sidecarFetch';
import {
  reduceEgressState,
  useEgressReport,
  type EgressUiState,
} from '../../lib/egressReport';

const mockedFetch = vi.mocked(sidecarFetch);

describe('FirstScreen egress generations', () => {
  afterEach(() => {
    vi.useRealTimers();
    mockedFetch.mockReset();
  });

  it('ignores completion and timeout from a superseded generation', () => {
    const current: EgressUiState = { kind: 'loading', generation: 2 };
    const staleMeasured = reduceEgressState(current, {
      type: 'resolved',
      generation: 1,
      state: {
        kind: 'error',
        generation: 1,
        reason: 'TIMEOUT',
        code: 'TIMEOUT',
      },
    });
    const staleTimeout = reduceEgressState(current, {
      type: 'resolved',
      generation: 1,
      state: {
        kind: 'error',
        generation: 1,
        reason: 'TIMEOUT',
        code: 'TIMEOUT',
      },
    });

    expect(staleMeasured).toBe(current);
    expect(staleTimeout).toBe(current);
  });

  it('cleans timers listeners and requests during unmount and StrictMode remount', async () => {
    vi.useFakeTimers();
    const signals: AbortSignal[] = [];
    mockedFetch.mockImplementation((_path, init) => {
      signals.push(init?.signal as AbortSignal);
      return new Promise<Response>(() => undefined);
    });

    const { unmount } = renderHook(() => useEgressReport(), {
      wrapper: StrictMode,
    });
    expect(signals.length).toBeGreaterThanOrEqual(2);
    unmount();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(signals.every(signal => signal.aborted)).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
