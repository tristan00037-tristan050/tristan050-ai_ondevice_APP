import { useEffect, useRef } from 'react';
import type { ProblemDetail } from '../../lib/accounting_review/contracts';

interface RuleConflictDialogProps {
  problem: ProblemDetail;
  pending: boolean;
  onDecision: (decision: 'KEEP_EXISTING' | 'REPLACE_WITH_NEW') => void;
  onCancel: () => void;
}

export function RuleConflictDialog({ problem, pending, onDecision, onCancel }: RuleConflictDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const replaceRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  if (!problem.conflict_id || !problem.conflict_version) return null;
  return (
    <div className="review-dialog-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget && !pending) onCancel();
    }}>
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rule-conflict-title"
        aria-describedby="rule-conflict-description"
        className="review-dialog"
        onKeyDown={event => {
          if (event.key === 'Escape' && !pending) onCancel();
          if (event.key === 'Tab') {
            const first = cancelRef.current;
            const last = replaceRef.current;
            if (!first || !last) return;
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <h2 id="rule-conflict-title">기존 거래처 제안 규칙이 있습니다</h2>
        <p id="rule-conflict-description">
          이 거래만 새 계정으로 저장하거나, 다음 거래부터 제안할 계정도 새 선택으로 바꿀 수 있습니다.
        </p>
        <dl className="review-dialog__comparison">
          <div><dt>기존 제안</dt><dd>{problem.existing_account_id ?? '확인 불가'}</dd></div>
          <div><dt>새 선택</dt><dd>{problem.proposed_account_id ?? '확인 불가'}</dd></div>
        </dl>
        <div className="review-dialog__actions">
          <button ref={cancelRef} type="button" disabled={pending} onClick={onCancel}>취소</button>
          <button type="button" disabled={pending} onClick={() => onDecision('KEEP_EXISTING')}>기존 제안 유지</button>
          <button ref={replaceRef} type="button" className="button-primary" disabled={pending} onClick={() => onDecision('REPLACE_WITH_NEW')}>
            {pending ? '저장 중' : '새 계정으로 제안 변경'}
          </button>
        </div>
      </section>
    </div>
  );
}
