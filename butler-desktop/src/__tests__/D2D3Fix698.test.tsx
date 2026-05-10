vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { App } from '../App';
import { AccountingModal } from '../components/chat/AccountingModal';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ── Sidecar ready check (기본) ────────────────────────────────────────────────

describe('Sidecar ready check', () => {
  it('test_sidecar_loading_overlay_shown_before_ready', async () => {
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));
    render(<App />);
    await waitFor(() => screen.getByTestId('sidecar-loading'));
    expect(screen.getByTestId('sidecar-loading')).toBeInTheDocument();
  });

  it('test_sidecar_loading_overlay_disappears_when_health_ok', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"status":"ok"}', { status: 200 })
    );
    render(<App />);
    await waitFor(
      () => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument(),
      { timeout: 3000 }
    );
  });
});

// ── Wall-clock timeout 정확성 (codex P2) ─────────────────────────────────────
//
// failTimer = setTimeout(setSidecarFailed, 60_000) — tick 카운터 방식 아님.
// fake timer로 정확히 60_000 ms 진행 → sidecar-failed 출현을 검증.

/** AbortSignal을 존중하는 fetch 목 — abort 시 AbortError 발생 */
function makeAbortAwareFetchMock() {
  return vi.fn().mockImplementation((_url: unknown, opts?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      const signal = opts?.signal as AbortSignal | undefined;
      if (signal?.aborted) {
        reject(new DOMException('The operation was aborted.', 'AbortError'));
        return;
      }
      signal?.addEventListener('abort', () =>
        reject(new DOMException('The operation was aborted.', 'AbortError'))
      );
    });
  });
}

describe('Sidecar wall-clock timeout (codex P2)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it(
    'test_sidecar_fail_timer_fires_exactly_at_60s_not_180s',
    async () => {
      // failTimer = setTimeout(setSidecarFailed, 60_000)
      // 이전 방식(tick 기반)이라면 최대 180 s 가 걸림 — 60 s 에 발화해야 한다
      vi.useFakeTimers({ now: 0 });
      vi.spyOn(global, 'fetch').mockImplementation(makeAbortAwareFetchMock());

      render(<App />);

      // t = 59_999 ms → 아직 실패하면 안 됨
      await act(async () => {
        vi.advanceTimersByTime(59_999);
      });
      expect(screen.queryByTestId('sidecar-failed')).not.toBeInTheDocument();

      // t = 60_000 ms → failTimer 발화 → sidecar-failed 출현
      await act(async () => {
        vi.advanceTimersByTime(1);
      });
      expect(screen.getByTestId('sidecar-failed')).toBeInTheDocument();
    },
    15_000
  );

  it(
    'test_sidecar_elapsed_counter_reflects_wall_clock',
    async () => {
      // sidecarElapsed = Math.floor((Date.now() - startMs) / 1000)
      // vi.advanceTimersByTimeAsync → timer와 microtask를 교대로 실행
      // abort-aware 목 → 각 poll 사이클(1500ms abort + 500ms retry ≈ 2s)이 실제 실행됨
      vi.useFakeTimers({ now: 0 });
      vi.spyOn(global, 'fetch').mockImplementation(makeAbortAwareFetchMock());

      render(<App />);

      // 첫 번째 poll 시작 시 elapsed = 0
      const elBefore = screen.getByTestId('sidecar-elapsed');
      expect(elBefore.textContent).toContain('0초 경과');

      // 20 s 진행 — advanceTimersByTimeAsync가 timer↔microtask를 번갈아 플러시
      // → poll 사이클이 ~10회 실행 → setSidecarElapsed(≥10) 호출
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000);
      });

      const elAfter = screen.getByTestId('sidecar-elapsed');
      const displayed = parseInt(elAfter.textContent ?? '0', 10);
      // wall-clock 기반: 20 s 진행 → 표시값 ≥ 10 (각 poll 사이클 ≈ 2s, 허용 오차 포함)
      expect(displayed).toBeGreaterThanOrEqual(10);
    },
    15_000
  );

  it(
    'test_sidecar_not_failed_when_health_ok_well_before_60s',
    async () => {
      // health 가 즉시 ok → sidecarFailed 절대 발화하면 안 됨
      vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response('{"status":"ok"}', { status: 200 })
      );

      render(<App />);

      await waitFor(
        () => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument(),
        { timeout: 3000 }
      );
      expect(screen.queryByTestId('sidecar-failed')).not.toBeInTheDocument();
    },
    10_000
  );
});

// ── Card 5 헤더 이모지 → Calculator 아이콘 ────────────────────────────────────

describe('Card 5 header Calculator icon', () => {
  it('test_accounting_modal_header_has_calculator_svg_not_emoji', () => {
    render(<AccountingModal onClose={() => {}} />);
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading.textContent).not.toContain('💰');
    const svg = heading.querySelector('svg');
    expect(svg).toBeTruthy();
  });
});
