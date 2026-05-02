import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProgressOverlay } from '../components/ProgressOverlay';
import type { SSEEvent } from '../types';

describe('ProgressOverlay', () => {
  it('test_happy_chunk_progress_updates_progressbar', () => {
    const events: SSEEvent[] = [
      { type: 'chunk_progress', data: { current: 4, total: 8, phase: 2, total_phases: 4, est_remaining_sec: 45 } },
    ];
    render(<ProgressOverlay visible events={events} onCancel={vi.fn()} />);
    const bar = screen.getByTestId('progress-bar') as HTMLProgressElement;
    expect(bar).toBeInTheDocument();
    expect(Number(bar.value)).toBe(50);
    expect(screen.getByTestId('phase-label').textContent).toMatch(/청크 분석/);
  });

  it('test_happy_complete_event_transitions_to_result', () => {
    const events: SSEEvent[] = [
      { type: 'complete', data: { result_path: '/tmp/result.json' } },
    ];
    render(<ProgressOverlay visible events={events} onCancel={vi.fn()} />);
    expect(screen.getByTestId('progress-overlay')).toHaveAttribute('data-state', 'complete');
    expect(screen.getByTestId('complete-msg')).toBeInTheDocument();
  });

  it('test_boundary_heartbeat_keeps_ui_alive', () => {
    const events: SSEEvent[] = [
      { type: 'heartbeat', data: { elapsed_sec: 45 } },
    ];
    render(<ProgressOverlay visible events={events} onCancel={vi.fn()} />);
    expect(screen.getByTestId('progress-overlay')).toHaveAttribute('data-state', 'heartbeat');
    expect(screen.getByTestId('heartbeat-msg').textContent).toMatch(/응답 대기 중/);
    expect(screen.getByTestId('heartbeat-msg').textContent).toMatch(/45/);
  });

  it('test_adv_cancel_button_aborts_request', () => {
    const onCancel = vi.fn();
    render(<ProgressOverlay visible events={[]} onCancel={onCancel} />);
    fireEvent.click(screen.getByTestId('cancel-btn'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('test_adv_chunk_timeout_shows_correct_message', () => {
    const events: SSEEvent[] = [
      { type: 'cancelled', data: { reason: 'chunk_timeout', partial_path: '' } },
    ];
    render(<ProgressOverlay visible events={events} onCancel={vi.fn()} />);
    expect(screen.getByTestId('cancelled-msg').textContent).toMatch(/너무 오래 걸려/);
  });

  it('test_adv_partial_result_button_opens_partial', () => {
    const onViewPartial = vi.fn();
    const events: SSEEvent[] = [
      { type: 'cancelled', data: { reason: 'hard_timeout', partial_path: '/tmp/partial.json' } },
    ];
    render(<ProgressOverlay visible events={events} onCancel={vi.fn()} onViewPartial={onViewPartial} />);
    expect(screen.getByTestId('cancelled-msg').textContent).toMatch(/180초/);
    const partialBtn = screen.getByTestId('partial-result-btn');
    expect(partialBtn).toBeInTheDocument();
    fireEvent.click(partialBtn);
    expect(onViewPartial).toHaveBeenCalledWith('/tmp/partial.json');
  });
});
