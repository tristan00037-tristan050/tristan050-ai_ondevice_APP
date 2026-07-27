import React, { useEffect, useRef } from 'react';
import { egressBadgeView } from '../EgressBadge';
import type { EgressUiState } from '../../lib/egressReport';

type Props = Readonly<{
  state: EgressUiState;
  onRefresh: () => void;
  onClose: () => void;
}>;

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function EgressMonitor({ state, onRefresh, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const view = egressBadgeView(state);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <>
      <div
        className="egress-monitor-backdrop"
        data-testid="egress-monitor-backdrop"
        onMouseDown={event => {
          if (event.target === event.currentTarget) onClose();
        }}
      />
      <div
        ref={panelRef}
        className="egress-monitor-panel"
        data-testid="egress-monitor-panel"
        data-generation={state.generation}
        role="dialog"
        aria-modal="true"
        aria-labelledby="egress-monitor-title"
        tabIndex={-1}
      >
        <header>
          <div>
            <p>온디바이스 네트워크 측정</p>
            <h2 id="egress-monitor-title">외부 전송 상태</h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            data-testid="egress-monitor-close"
            onClick={onClose}
            aria-label="외부 전송 상태 닫기"
          >
            ×
          </button>
        </header>

        <div className="egress-monitor-summary" data-tone={view.tone} role="status">
          <strong>{view.label}</strong>
        </div>

        {state.kind === 'ready' && (
          <dl>
            <div>
              <dt>외부 전송 바이트</dt>
              <dd data-testid="egress-monitor-bytes">{state.report.egressBytesTotal} bytes</dd>
            </div>
            <div>
              <dt>외부 요청 수</dt>
              <dd>{state.report.externalRequestCount}</dd>
            </div>
            <div>
              <dt>원본 파일 외부 전송</dt>
              <dd>{state.report.rawFileSentExternal ? '감지됨' : '감지되지 않음'}</dd>
            </div>
            <div>
              <dt>측정 시각</dt>
              <dd data-testid="egress-monitor-measured-at">{state.report.measuredAt}</dd>
            </div>
          </dl>
        )}

        <p className="egress-monitor-help">
          측정값이 없거나 오래되었거나 검증에 실패하면 0으로 대체하지 않습니다.
        </p>
        <button type="button" className="egress-monitor-refresh" onClick={onRefresh}>
          다시 확인
        </button>
      </div>
    </>
  );
}
