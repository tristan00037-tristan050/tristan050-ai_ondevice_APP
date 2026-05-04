import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { EgressMonitor } from '../components/chat/EgressMonitor';

const PASS_REPORT = {
  schema_version: 'egress_report.v2',
  task_id: 'test-task-123',
  mode: 'local_only',
  raw_file_sent_external: false,
  raw_text_logged: false,
  egress_bytes_total: 0,
  dns_requests: 0,
  http_requests: 0,
  https_requests: 0,
  telemetry_enabled: false,
  crash_report_enabled: false,
  update_check_enabled: false,
  verdict: 'PASS',
  generated_at: '2026-05-03T12:00:00Z',
};

function mockFetch(report: object) {
  global.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(report), {
      headers: { 'Content-Type': 'application/json' },
    })
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('EgressMonitor', () => {
  it('test_happy_panel_renders_with_dialog_role', async () => {
    mockFetch(PASS_REPORT);
    render(<EgressMonitor onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByTestId('egress-monitor-panel')).toBeInTheDocument();
  });

  it('test_happy_verdict_pass_displayed', async () => {
    mockFetch(PASS_REPORT);
    render(<EgressMonitor onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('egress-monitor-verdict')).toBeInTheDocument();
    });
    expect(screen.getByTestId('egress-monitor-verdict').textContent).toContain('PASS');
  });

  it('test_happy_mode_local_only_displayed', async () => {
    mockFetch(PASS_REPORT);
    render(<EgressMonitor onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('egress-monitor-mode')).toBeInTheDocument();
    });
    expect(screen.getByTestId('egress-monitor-mode').textContent).toContain('Local-only');
  });

  it('test_happy_download_button_present', async () => {
    mockFetch(PASS_REPORT);
    render(<EgressMonitor onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('egress-monitor-download')).toBeInTheDocument();
    });
  });

  it('test_happy_backdrop_click_calls_onClose', () => {
    mockFetch(PASS_REPORT);
    const onClose = vi.fn();
    render(<EgressMonitor onClose={onClose} />);
    fireEvent.click(screen.getByTestId('egress-monitor-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('test_happy_close_button_calls_onClose', () => {
    mockFetch(PASS_REPORT);
    const onClose = vi.fn();
    render(<EgressMonitor onClose={onClose} />);
    fireEvent.click(screen.getByTestId('egress-monitor-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('test_boundary_fail_verdict_displayed', async () => {
    const failReport = { ...PASS_REPORT, verdict: 'FAIL', egress_bytes_total: 1024 };
    mockFetch(failReport);
    render(<EgressMonitor onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('egress-monitor-verdict').textContent).toContain('FAIL');
    });
  });

  it('test_boundary_fetch_error_shows_error_message', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
    render(<EgressMonitor onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('egress-monitor-error')).toBeInTheDocument();
    });
  });
});
