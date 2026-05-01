import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EgressBadge } from '../components/EgressBadge';

describe('EgressBadge', () => {
  afterEach(() => vi.restoreAllMocks());

  it('test_happy_default_state_shows_local_only', () => {
    render(<EgressBadge />);
    const badge = screen.getByTestId('egress-badge');
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/Local-only Mode/);
    expect(badge.textContent).toMatch(/🔒/);
  });

  it('test_happy_click_opens_detail_panel', () => {
    render(<EgressBadge />);
    expect(screen.queryByTestId('egress-panel')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('egress-badge'));
    expect(screen.getByTestId('egress-panel')).toBeInTheDocument();
    expect(screen.getByTestId('egress-panel').textContent).toMatch(/Egress Monitor/);
  });

  it('test_boundary_zero_bytes_displayed_correctly', () => {
    render(<EgressBadge stats={{ egress_bytes_total: 0 }} />);
    fireEvent.click(screen.getByTestId('egress-badge'));
    expect(screen.getByTestId('egress-bytes').textContent).toBe('0');
    expect(screen.getByTestId('egress-verdict').textContent).toBe('PASS');
  });

  it('test_adv_download_button_creates_json_file', () => {
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:test-url');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(<EgressBadge />);
    fireEvent.click(screen.getByTestId('egress-badge'));
    fireEvent.click(screen.getByTestId('download-btn'));

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
  });

  it('test_adv_blocked_egress_shows_red_warning', () => {
    render(<EgressBadge isBlocked={true} />);
    const badge = screen.getByTestId('egress-badge');
    expect(badge.textContent).toMatch(/⚠️|차단됨/);
    expect(badge.style.background).toBe('rgb(245, 34, 45)');
  });
});
