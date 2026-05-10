vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App } from '../App';
import { AccountingModal } from '../components/chat/AccountingModal';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ── Sidecar ready check ───────────────────────────────────────────────────────

describe('Sidecar ready check', () => {
  it('test_sidecar_loading_overlay_shown_before_ready', async () => {
    // Health endpoint never responds → overlay persists
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));
    render(<App />);
    await waitFor(() => screen.getByTestId('sidecar-loading'));
    expect(screen.getByTestId('sidecar-loading')).toBeInTheDocument();
  });

  it('test_sidecar_loading_overlay_disappears_when_health_ok', async () => {
    // Health endpoint returns ok immediately → overlay removed
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{"status":"ok"}', { status: 200 })
    );
    render(<App />);
    // Overlay should disappear once health resolves
    await waitFor(() => expect(screen.queryByTestId('sidecar-loading')).not.toBeInTheDocument(), {
      timeout: 3000,
    });
  });
});

// ── Card 5 헤더 이모지 → Calculator 아이콘 ────────────────────────────────────

describe('Card 5 header Calculator icon', () => {
  it('test_accounting_modal_header_has_calculator_svg_not_emoji', () => {
    render(<AccountingModal onClose={() => {}} />);

    // h2 텍스트에 💰 이모지가 없어야 함
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading.textContent).not.toContain('💰');

    // Calculator SVG 아이콘이 헤더 안에 존재해야 함
    const svg = heading.querySelector('svg');
    expect(svg).toBeTruthy();
  });
});
