import { useEffect, useRef, useState } from 'react';
import { deactivateLearnedRule, getLearnedRules } from '../../lib/accounting_review/client';
import type { LearnedRule } from '../../lib/accounting_review/contracts';

interface LearnedRuleSettingsProps {
  onClose: () => void;
}

export function LearnedRuleSettings({ onClose }: LearnedRuleSettingsProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [rules, setRules] = useState<LearnedRule[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [status, setStatus] = useState('거래처 제안 규칙을 불러오는 중입니다.');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    closeRef.current?.focus();
    let active = true;
    getLearnedRules()
      .then(items => {
        if (!active) return;
        setRules(items);
        setStatus(items.length ? '' : '등록된 거래처 제안 규칙이 없습니다.');
      })
      .catch(() => {
        if (active) setError('제안 규칙을 불러오지 못했습니다. 규칙 목록을 변경하지 않았습니다.');
      });
    return () => { active = false; };
  }, []);

  const deactivate = async (rule: LearnedRule) => {
    setPending(rule.rule_id);
    setError(null);
    try {
      await deactivateLearnedRule(rule);
      setRules(current => current.map(item => item.rule_id === rule.rule_id
        ? { ...item, state: 'INACTIVE_USER', resource_version: item.resource_version + 1 }
        : item));
      setStatus('제안 규칙을 비활성화했습니다.');
    } catch {
      setError('제안 규칙을 비활성화하지 못했습니다. 서버에서 최신 목록을 다시 확인해 주세요.');
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="review-dialog-backdrop">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="learned-rules-title"
        className="review-dialog review-dialog--wide"
        onKeyDown={event => { if (event.key === 'Escape' && !pending) onClose(); }}
      >
        <div className="review-dialog__header">
          <div>
            <h2 id="learned-rules-title">거래처 제안 규칙</h2>
            <p>규칙은 계정을 자동 확정하지 않고 다음 거래에서 제안만 합니다.</p>
          </div>
          <button ref={closeRef} type="button" aria-label="거래처 제안 규칙 닫기" onClick={onClose}>닫기</button>
        </div>
        {error && <p role="alert" className="review-error">{error}</p>}
        {status && <p role="status">{status}</p>}
        <ul className="learned-rule-list">
          {rules.map(rule => (
            <li key={rule.rule_id}>
              <div>
                <strong>{rule.descriptor_display}</strong>
                <span>계정 ID {rule.account_id}</span>
                <span>{rule.state === 'ACTIVE_SUGGESTION' ? '제안 중' : '비활성'}</span>
              </div>
              <button
                type="button"
                disabled={rule.state !== 'ACTIVE_SUGGESTION' || pending !== null}
                onClick={() => deactivate(rule)}
              >
                {pending === rule.rule_id ? '처리 중' : '비활성화'}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
