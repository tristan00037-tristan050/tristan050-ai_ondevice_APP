import React, { forwardRef } from 'react';
import {
  isVerifiedZero,
  type EgressUiState,
} from '../lib/egressReport';

type Props = Readonly<{
  state: EgressUiState;
  onOpenDetails: () => void;
}>;

export type EgressBadgeView = Readonly<{
  label: '확인 중' | '확인 실패' | '다시 확인 필요' | `밖으로 나간 것 ${number}`;
  tone: 'loading' | 'error' | 'stale' | 'safe' | 'warning';
  ariaLabel: string;
}>;

export function egressBadgeView(state: EgressUiState): EgressBadgeView {
  if (state.kind === 'loading') {
    return { label: '확인 중', tone: 'loading', ariaLabel: '외부 전송 상태 확인 중' };
  }
  if (state.kind === 'error') {
    return { label: '확인 실패', tone: 'error', ariaLabel: '외부 전송 상태 확인 실패' };
  }
  if (state.kind === 'stale') {
    return {
      label: '다시 확인 필요',
      tone: 'stale',
      ariaLabel: state.lastMeasuredAt
        ? `외부 전송 상태 다시 확인 필요, 마지막 측정 시각 ${state.lastMeasuredAt}`
        : '외부 전송 상태 다시 확인 필요',
    };
  }
  const { report } = state;
  if (isVerifiedZero(report)) {
    return {
      label: '밖으로 나간 것 0',
      tone: 'safe',
      ariaLabel: `밖으로 나간 것 0 바이트, 측정 시각 ${report.measuredAt}`,
    };
  }
  if (report.verdict === 'FAIL' && report.egressBytesTotal > 0) {
    return {
      label: `밖으로 나간 것 ${report.egressBytesTotal}`,
      tone: 'warning',
      ariaLabel: `밖으로 나간 것 ${report.egressBytesTotal} 바이트, 측정 시각 ${report.measuredAt}`,
    };
  }
  return {
    label: '확인 실패',
    tone: 'error',
    ariaLabel: '외부 전송 측정값의 안전한 표시 조건을 확인하지 못함',
  };
}

export const EgressBadge = forwardRef<HTMLButtonElement, Props>(
  function EgressBadge({ state, onOpenDetails }, ref) {
    const view = egressBadgeView(state);
    return (
      <button
        ref={ref}
        type="button"
        className="egress-badge"
        data-tone={view.tone}
        data-generation={state.generation}
        data-testid="egress-badge"
        onClick={onOpenDetails}
        aria-label={view.ariaLabel}
      >
        <span aria-hidden="true">{view.tone === 'safe' ? '✓' : view.tone === 'loading' ? '…' : '!'}</span>
        {view.label}
      </button>
    );
  },
);
