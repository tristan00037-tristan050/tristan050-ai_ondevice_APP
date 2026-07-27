import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { EgressMonitor } from '../components/chat/EgressMonitor';
import type { EgressUiState } from '../lib/egressReport';

const STATE: EgressUiState = {
  kind: 'measured',
  generation: 7,
  report: Object.freeze({
    schemaVersion: 'butler.egress.report.v3',
    measurement: 'MEASURED',
    value: 0,
    runId: 'run-modal',
    measurementGeneration: 7,
    measurementStartedAt: '2026-07-27T01:00:00Z',
    measuredAt: '2026-07-27T01:00:01Z',
    freshUntil: '2026-07-27T01:01:01Z',
    egressBytesTotal: 0,
    externalRequestCount: 0,
    rawFileSentExternal: false,
    verdict: 'PASS',
    receiptRunId: 'run-modal',
    receiptKeyId: 'butler-egress-verifier-test-v1',
    receiptAlgorithm: 'Ed25519',
    receiptPolicyVersion: 'egress-policy-2026.1',
    receiptDigest: `sha256:${'b'.repeat(64)}`,
    receiptSignature: 'B'.repeat(86),
  }),
};

describe('EgressMonitor', () => {
  it('renders the same immutable generation without fetching', () => {
    render(<EgressMonitor state={STATE} onRefresh={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: '외부 전송 상태' })).toHaveAttribute(
      'data-generation',
      '7',
    );
    expect(screen.getByTestId('egress-monitor-bytes')).toHaveTextContent('0 bytes');
    expect(screen.getByTestId('egress-monitor-measurement')).toHaveTextContent(
      'MEASURED',
    );
    expect(screen.getByTestId('egress-monitor-measured-at')).toHaveTextContent(
      STATE.report.measuredAt,
    );
  });

  it('discloses that STATIC_BETA is not measurement and renders no byte table', () => {
    render(
      <EgressMonitor
        state={{
          kind: 'unmeasured',
          generation: 8,
          source: 'STATIC_BETA',
        }}
        onRefresh={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId('egress-monitor-unmeasured')).toHaveTextContent(
      'STATIC_BETA 상수는 안전 판정에 사용하지 않습니다.',
    );
    expect(screen.queryByTestId('egress-monitor-bytes')).not.toBeInTheDocument();
  });

  it('closes by Escape, close button and backdrop', () => {
    const onClose = vi.fn();
    render(<EgressMonitor state={STATE} onRefresh={vi.fn()} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByTestId('egress-monitor-close'));
    fireEvent.mouseDown(screen.getByTestId('egress-monitor-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('calls the provider refresh callback', () => {
    const onRefresh = vi.fn();
    render(<EgressMonitor state={STATE} onRefresh={onRefresh} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '다시 확인' }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
