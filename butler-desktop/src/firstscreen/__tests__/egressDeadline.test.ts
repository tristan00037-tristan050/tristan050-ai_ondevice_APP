import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SidecarDeadlineError,
  withDeadline,
} from '../../lib/sidecarFetch';

describe('FirstScreen egress deadline', () => {
  afterEach(() => vi.useRealTimers());

  it('keeps loading before the explicit egress deadline', async () => {
    vi.useFakeTimers();
    let settled = false;
    const observed = withDeadline(
      () => new Promise<never>(() => undefined),
      { deadlineMs: 8_000 },
    ).then(() => null, error => {
      settled = true;
      return error;
    });

    await vi.advanceTimersByTimeAsync(7_999);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await expect(observed).resolves.toBeInstanceOf(SidecarDeadlineError);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('terminates with TIMEOUT after a never-settling adapter crosses its deadline', async () => {
    vi.useFakeTimers();
    const pending = withDeadline(
      () => new Promise<never>(() => undefined),
      { deadlineMs: 8_000 },
    );
    const observed = pending.catch(error => error);

    await vi.advanceTimersByTimeAsync(8_000);
    const error = await observed;
    expect(error).toBeInstanceOf(SidecarDeadlineError);
    expect(error).toMatchObject({ code: 'SIDECAR_DEADLINE_EXCEEDED' });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not classify an external abort as TIMEOUT', async () => {
    vi.useFakeTimers();
    const external = new AbortController();
    const reason = new DOMException('user refresh', 'AbortError');
    const pending = withDeadline(
      () => new Promise<never>(() => undefined),
      { deadlineMs: 8_000, externalSignal: external.signal },
    );
    const observed = pending.catch(error => error);

    external.abort(reason);
    await expect(observed).resolves.toBe(reason);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1.5])(
    'rejects invalid deadline budget %s before starting transport',
    async deadlineMs => {
      const operation = vi.fn();
      await expect(withDeadline(operation, { deadlineMs }))
        .rejects.toThrow('DEADLINE_MS_INVALID');
      expect(operation).not.toHaveBeenCalled();
    },
  );

  it('does not start transport for an already-aborted caller', async () => {
    const external = new AbortController();
    const reason = new DOMException('unmounted', 'AbortError');
    external.abort(reason);
    const operation = vi.fn();

    await expect(withDeadline(operation, {
      deadlineMs: 8_000,
      externalSignal: external.signal,
    })).rejects.toBe(reason);
    expect(operation).not.toHaveBeenCalled();
  });
});
