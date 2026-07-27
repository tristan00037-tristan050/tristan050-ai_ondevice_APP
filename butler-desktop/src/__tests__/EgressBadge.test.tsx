import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { EgressBadge } from '../components/EgressBadge';
import type { EgressReport, EgressUiState } from '../lib/egressReport';

const ZERO_REPORT: EgressReport = Object.freeze({
  schemaVersion: 'butler.egress.report.v3',
  runId: 'run-zero',
  measurementGeneration: 1,
  measurementStartedAt: '2026-07-27T01:00:00Z',
  measuredAt: '2026-07-27T01:00:01Z',
  freshUntil: '2026-07-27T01:01:01Z',
  egressBytesTotal: 0,
  externalRequestCount: 0,
  rawFileSentExternal: false,
  verdict: 'PASS',
  receiptRunId: 'run-zero',
  receiptKeyId: 'butler-egress-verifier-test-v1',
  receiptAlgorithm: 'Ed25519',
  receiptPolicyVersion: 'egress-policy-2026.1',
  receiptDigest: `sha256:${'a'.repeat(64)}`,
  receiptSignature: 'A'.repeat(86),
});

function renderState(state: EgressUiState, onOpenDetails = vi.fn()) {
  render(<EgressBadge state={state} onOpenDetails={onOpenDetails} />);
  return onOpenDetails;
}

describe('EgressBadge', () => {
  it.each([
    [{ kind: 'loading', generation: 1 }, '확인 중'],
    [{ kind: 'error', generation: 1, code: 'HTTP_ERROR' }, '확인 실패'],
    [{ kind: 'stale', generation: 1, code: 'FRESHNESS_EXPIRED' }, '다시 확인 필요'],
  ] as const)('does not turn non-ready state into zero', (state, label) => {
    renderState(state);
    expect(screen.getByTestId('egress-badge')).toHaveTextContent(label);
    expect(screen.getByTestId('egress-badge')).not.toHaveTextContent('밖으로 나간 것 0');
  });

  it('shows zero only for a fresh internally consistent PASS report', () => {
    renderState({ kind: 'ready', generation: 2, report: ZERO_REPORT });
    const badge = screen.getByTestId('egress-badge');
    expect(badge).toHaveTextContent('밖으로 나간 것 0');
    expect(badge).toHaveAttribute('data-tone', 'safe');
    expect(badge).toHaveAccessibleName(/0 바이트.*측정 시각/);
  });

  it('shows positive bytes as warning and opens the shared modal', () => {
    const onOpen = renderState({
      kind: 'ready',
      generation: 3,
      report: {
        ...ZERO_REPORT,
        runId: 'run-positive',
        receiptRunId: 'run-positive',
        egressBytesTotal: 2048,
        externalRequestCount: 1,
        verdict: 'FAIL',
      },
    });
    const badge = screen.getByTestId('egress-badge');
    expect(badge).toHaveTextContent('밖으로 나간 것 2048');
    expect(badge).toHaveAttribute('data-tone', 'warning');
    fireEvent.click(badge);
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it.each([
    {
      runId: 'run-request',
      externalRequestCount: 1,
      rawFileSentExternal: false,
      accessible: /외부 요청 1건/,
    },
    {
      runId: 'run-raw-file',
      externalRequestCount: 0,
      rawFileSentExternal: true,
      accessible: /원본 파일 외부 전송 관측/,
    },
  ])('warns for every verified zero-byte FAIL: $runId', report => {
    renderState({
      kind: 'ready',
      generation: 4,
      report: {
        ...ZERO_REPORT,
        runId: report.runId,
        receiptRunId: report.runId,
        externalRequestCount: report.externalRequestCount,
        rawFileSentExternal: report.rawFileSentExternal,
        verdict: 'FAIL',
      },
    });
    const badge = screen.getByTestId('egress-badge');
    expect(badge).toHaveTextContent('외부 전송 감지');
    expect(badge).toHaveAttribute('data-tone', 'warning');
    expect(badge).toHaveAccessibleName(report.accessible);
    expect(badge).not.toHaveTextContent('확인 실패');
  });
});
