import React, { useEffect } from 'react';
import type { SSEEvent } from '../types';

interface ProgressOverlayProps {
  visible: boolean;
  events: SSEEvent[];
  onCancel: () => void;
  onViewPartial?: (path: string) => void;
  onResult?: (result: unknown) => void;
}

const CANCELLED_MESSAGES: Record<string, string> = {
  chunk_timeout: '한 청크가 너무 오래 걸려 중단됨',
  hard_timeout: '전체 시간 초과 (180초)',
  user_cancel: '사용자 중단',
};

export function ProgressOverlay({ visible, events, onCancel, onViewPartial, onResult }: ProgressOverlayProps) {
  // complete 이벤트 도착 시 onResult 자동 호출 — App.tsx SSE 루프의 백업
  useEffect(() => {
    if (!visible) return;
    const completeEvt = events.find(e => e.type === 'complete');
    if (completeEvt) onResult?.(completeEvt.data);
  }, [events, visible, onResult]);

  if (!visible) return null;

  const lastEvent = events[events.length - 1] as SSEEvent | undefined;

  if (!lastEvent) {
    return (
      <div data-testid="progress-overlay">
        <p>작업 준비 중…</p>
        <button data-testid="cancel-btn" onClick={onCancel}>중단</button>
      </div>
    );
  }

  if (lastEvent.type === 'complete') {
    return (
      <div data-testid="progress-overlay" data-state="complete">
        <p data-testid="complete-msg">작업이 완료되었습니다.</p>
        <button onClick={() => onResult?.(lastEvent.data)}>결과 보기</button>
      </div>
    );
  }

  if (lastEvent.type === 'cancelled') {
    const reason = (lastEvent.data.reason as string) ?? 'user_cancel';
    const partialPath = lastEvent.data.partial_path as string | undefined;
    const msg = CANCELLED_MESSAGES[reason] ?? '작업이 중단되었습니다.';
    return (
      <div data-testid="progress-overlay" data-state="cancelled">
        <p data-testid="cancelled-msg">{msg}</p>
        {partialPath && (
          <button data-testid="partial-result-btn" onClick={() => onViewPartial?.(partialPath)}>
            부분 결과 보기
          </button>
        )}
        <button data-testid="cancel-btn" onClick={onCancel}>닫기</button>
      </div>
    );
  }

  if (lastEvent.type === 'error') {
    return (
      <div data-testid="progress-overlay" data-state="error">
        <p data-testid="error-msg">오류: {lastEvent.data.message as string}</p>
        <button data-testid="cancel-btn" onClick={onCancel}>닫기</button>
      </div>
    );
  }

  if (lastEvent.type === 'heartbeat') {
    const elapsed = (lastEvent.data.elapsed_sec as number) ?? 0;
    return (
      <div data-testid="progress-overlay" data-state="heartbeat">
        <p data-testid="heartbeat-msg">응답 대기 중... ({elapsed}초 경과)</p>
        <button data-testid="cancel-btn" onClick={onCancel}>중단</button>
      </div>
    );
  }

  // chunk_progress / phase_start / chunk_done / reduce_start / verify_start
  const current = (lastEvent.data.current as number) ?? 0;
  const total = (lastEvent.data.total as number) ?? 1;
  const phase = (lastEvent.data.phase as number) ?? 1;
  const totalPhases = (lastEvent.data.total_phases as number) ?? 4;
  const remaining = (lastEvent.data.est_remaining_sec as number) ?? 0;
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;

  const phaseLabel: Record<string, string> = {
    reduce_start: '결과 합치는 중',
    verify_start: '검증 중',
    phase_start: `단계 ${phase}/${totalPhases}: ${lastEvent.data.label ?? '처리 중'}`,
  };
  const label = phaseLabel[lastEvent.type] ?? `단계 ${phase}/${totalPhases}: 청크 분석 중`;

  return (
    <div data-testid="progress-overlay" data-state="progress">
      <p data-testid="phase-label">{label}</p>
      <progress data-testid="progress-bar" value={pct} max={100} style={{ width: '100%' }} />
      <p>{pct}% · {current}/{total} 청크 · 남은 시간 약 {remaining}초</p>
      <button data-testid="cancel-btn" onClick={onCancel}>중단</button>
    </div>
  );
}
