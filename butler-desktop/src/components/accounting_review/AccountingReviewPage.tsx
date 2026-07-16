import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AccountingReviewApiError,
  assignAccount,
  createAssignmentIntentKey,
  getChartRegistry,
  getReviewSummary,
  getRuntimeCapabilities,
  getUnaccountedPage,
  resolveRuleConflict,
} from '../../lib/accounting_review/client';
import type {
  AssignmentScope,
  ChartRegistryView,
  ProblemDetail,
  ReviewItem,
  ReviewSummary,
  RuntimeCapabilities,
} from '../../lib/accounting_review/contracts';
import { AccountCombobox } from './AccountCombobox';
import { LearnedRuleSettings } from './LearnedRuleSettings';
import { RuleConflictDialog } from './RuleConflictDialog';
import './accounting-review.css';

interface AccountingReviewPageProps {
  batchId: string;
  onBack: () => void;
}

interface ConflictState {
  txnId: string;
  problem: ProblemDetail;
}

function capabilityConsumed(capabilities: RuntimeCapabilities, capabilityId: string): boolean {
  return capabilities.capabilities.some(item => item.capability_id === capabilityId && item.status === 'CONSUMED');
}

function formatMoney(item: ReviewItem): string {
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency: item.money.currency,
    maximumFractionDigits: 0,
  }).format(item.money.minor_units);
}

const STATE_LABEL: Record<ReviewItem['review_state'], string> = {
  AUTO_PROPOSE: '자동 분류 제안',
  USER_RULE_SUGGESTED: '거래처 규칙 제안',
  REVIEW_REQUIRED: '직접 확인 필요',
};

export function AccountingReviewPage({ batchId, onBack }: AccountingReviewPageProps) {
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [registry, setRegistry] = useState<ChartRegistryView | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selections, setSelections] = useState<Record<string, string | null>>({});
  const [scopes, setScopes] = useState<Record<string, AssignmentScope>>({});
  const [intentKeys, setIntentKeys] = useState<Record<string, string>>({});
  const [pendingTxn, setPendingTxn] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const applyInitialSelections = useCallback((nextItems: ReviewItem[]) => {
    setSelections(current => {
      const updated = { ...current };
      nextItems.forEach(item => {
        if (!(item.txn_id in updated)) updated[item.txn_id] = item.suggestion?.account_id ?? null;
      });
      return updated;
    });
    setScopes(current => {
      const updated = { ...current };
      nextItems.forEach(item => {
        if (!(item.txn_id in updated)) updated[item.txn_id] = 'THIS_ONLY';
      });
      return updated;
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextCapabilities = await getRuntimeCapabilities();
      if (!capabilityConsumed(nextCapabilities, 'accounting.review_projection')) {
        throw new Error('REVIEW_PROJECTION_UNAVAILABLE');
      }
      const [nextSummary, firstPage] = await Promise.all([
        getReviewSummary(batchId),
        getUnaccountedPage(batchId),
      ]);
      if (nextSummary.batch_version !== firstPage.batch_version || nextSummary.registry_digest !== firstPage.registry_digest) {
        throw new Error('REVIEW_SNAPSHOT_MISMATCH');
      }
      const nextRegistry = await getChartRegistry(firstPage.registry_digest);
      if (nextRegistry.overlay_digest !== firstPage.overlay_digest) throw new Error('REGISTRY_OVERLAY_MISMATCH');
      setCapabilities(nextCapabilities);
      setSummary(nextSummary);
      setRegistry(nextRegistry);
      setItems(firstPage.items);
      setNextCursor(firstPage.next_cursor);
      setSelections({});
      setScopes({});
      setIntentKeys({});
      applyInitialSelections(firstPage.items);
    } catch {
      setError('계정 검토 데이터를 안전하게 불러오지 못했습니다. 분류 결과는 변경하지 않았습니다.');
    } finally {
      setLoading(false);
    }
  }, [applyInitialSelections, batchId]);

  useEffect(() => { void load(); }, [load]);

  const assignmentEnabled = capabilities ? capabilityConsumed(capabilities, 'accounting.user_assignment') : false;
  const ruleEnabled = capabilities ? capabilityConsumed(capabilities, 'accounting.user_rule_suggestion') : false;
  const ruleManagementEnabled = capabilities ? capabilityConsumed(capabilities, 'accounting.rule_management') : false;
  const accountById = useMemo(() => new Map(registry?.entries.map(entry => [entry.account_id, entry]) ?? []), [registry]);

  const completeTxn = (txnId: string, accountId: string) => {
    const accountName = accountById.get(accountId)?.display_name ?? '선택한 계정';
    setItems(current => current.filter(item => item.txn_id !== txnId));
    setIntentKeys(current => {
      const updated = { ...current };
      delete updated[txnId];
      return updated;
    });
    setSummary(current => current ? {
      ...current,
      batch_version: current.batch_version + 1,
      counts: { ...current.counts, user_assigned: current.counts.user_assigned + 1 },
    } : current);
    setAnnouncement(`${accountName}으로 저장했습니다.`);
  };

  const submit = async (item: ReviewItem) => {
    const accountId = selections[item.txn_id];
    if (!registry || !accountId || pendingTxn) return;
    const entry = accountById.get(accountId);
    if (!entry?.assignable) {
      setError('선택할 수 없는 계정입니다. 최신 계정 목록에서 다시 선택해 주세요.');
      return;
    }
    const scope = scopes[item.txn_id] ?? 'THIS_ONLY';
    if (scope === 'SAME_VENDOR_FUTURE' && !ruleEnabled) {
      setError('거래처 제안 규칙 기능을 확인할 수 없어 이번 거래에만 저장할 수 있습니다.');
      return;
    }
    let intentKey = intentKeys[item.txn_id];
    if (!intentKey) {
      intentKey = createAssignmentIntentKey();
      setIntentKeys(current => ({ ...current, [item.txn_id]: intentKey }));
    }
    setPendingTxn(item.txn_id);
    setError(null);
    try {
      const response = await assignAccount({
        txnId: item.txn_id,
        accountId,
        scope,
        registryDigest: registry.registry_digest,
        transactionVersion: item.transaction_version,
        intentKey,
      });
      completeTxn(item.txn_id, response.account_id);
      await load();
    } catch (caught) {
      if (caught instanceof AccountingReviewApiError) {
        if (caught.problem.code === 'LEARNED_RULE_CONFLICT' && caught.problem.conflict_id) {
          setConflict({ txnId: item.txn_id, problem: caught.problem });
        } else if (caught.problem.status === 412) {
          setAnnouncement('거래 정보가 바뀌어 최신 목록을 다시 불러옵니다. 저장은 다시 실행하지 않습니다.');
          await load();
        } else {
          setIntentKeys(current => {
            const updated = { ...current };
            delete updated[item.txn_id];
            return updated;
          });
          setError(caught.problem.safe_detail);
        }
      } else {
        setError('저장 결과를 확인하지 못했습니다. 같은 요청 키로 다시 시도할 수 있습니다.');
      }
    } finally {
      setPendingTxn(null);
    }
  };

  const resolveConflict = async (decision: 'KEEP_EXISTING' | 'REPLACE_WITH_NEW') => {
    if (!conflict?.problem.conflict_id || !conflict.problem.conflict_version) return;
    setPendingTxn(conflict.txnId);
    setError(null);
    try {
      const response = await resolveRuleConflict({
        conflictId: conflict.problem.conflict_id,
        conflictVersion: conflict.problem.conflict_version,
        decision,
      });
      completeTxn(conflict.txnId, response.account_id);
      setConflict(null);
      await load();
    } catch (caught) {
      setError(caught instanceof AccountingReviewApiError
        ? caught.problem.safe_detail
        : '규칙 충돌 처리 결과를 확인하지 못했습니다. 거래 목록을 새로 불러와 주세요.');
    } finally {
      setPendingTxn(null);
    }
  };

  const loadMore = async () => {
    if (!nextCursor || !summary || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await getUnaccountedPage(batchId, nextCursor);
      if (page.batch_version !== summary.batch_version) {
        setError('목록을 보는 동안 거래가 변경되었습니다. 중복 저장을 막기 위해 최신 목록을 다시 불러옵니다.');
        await load();
        return;
      }
      const existing = new Set(items.map(item => item.txn_id));
      const novel = page.items.filter(item => !existing.has(item.txn_id));
      setItems(current => [...current, ...novel]);
      setNextCursor(page.next_cursor);
      applyInitialSelections(novel);
    } catch {
      setError('다음 목록을 불러오지 못했습니다. 현재 목록은 그대로 유지합니다.');
    } finally {
      setLoadingMore(false);
    }
  };

  if (loading) return <div className="accounting-review-page" role="status">계정 검토 목록을 불러오는 중입니다.</div>;
  if (!summary || !registry || !capabilities) {
    return (
      <div className="accounting-review-page">
        <p role="alert" className="review-error">{error}</p>
        <div className="review-page-actions"><button type="button" onClick={onBack}>분류 결과로 돌아가기</button><button type="button" onClick={() => void load()}>다시 불러오기</button></div>
      </div>
    );
  }

  return (
    <section className="accounting-review-page" aria-labelledby="accounting-review-title">
      <div className="review-page-header">
        <div>
          <button type="button" className="button-link" onClick={onBack}>분류 결과로 돌아가기</button>
          <h2 id="accounting-review-title">계정 미확정 거래 검토</h2>
          <p>자동 제안은 확정이 아닙니다. 거래별로 계정과 적용 범위를 확인한 뒤 저장합니다.</p>
        </div>
        <button type="button" disabled={!ruleManagementEnabled} onClick={() => setRulesOpen(true)}>거래처 제안 규칙 관리</button>
      </div>

      <dl className="review-summary" aria-label="계정 검토 요약">
        <div><dt>직접 확인</dt><dd>{summary.counts.review_required}</dd></div>
        <div><dt>자동 제안</dt><dd>{summary.counts.auto_propose}</dd></div>
        <div><dt>규칙 제안</dt><dd>{summary.counts.user_rule_suggested}</dd></div>
        <div><dt>저장 완료</dt><dd>{summary.counts.user_assigned}</dd></div>
      </dl>

      {!assignmentEnabled && <p role="alert" className="review-warning">저장 기능 상태를 확인할 수 없어 선택과 저장을 잠갔습니다.</p>}
      {error && <p role="alert" className="review-error">{error}</p>}
      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>

      <div className="review-item-list">
        {items.length === 0 && <p role="status" className="review-empty">검토할 거래가 없습니다.</p>}
        {items.map(item => {
          const labelId = `account-label-${item.txn_id}`;
          const selectedId = selections[item.txn_id] ?? null;
          const isPending = pendingTxn === item.txn_id;
          return (
            <article className="review-item" key={item.txn_id} aria-busy={isPending}>
              <div className="review-item__transaction">
                <span className={`review-state review-state--${item.review_state.toLocaleLowerCase()}`}>{STATE_LABEL[item.review_state]}</span>
                <strong>{item.descriptor_display}</strong>
                <span>{item.booked_date}</span>
                <span className="review-item__money">{formatMoney(item)}</span>
                {item.suggestion && <small>{item.suggestion.safe_reason}</small>}
              </div>
              <div className="review-item__decision">
                <label id={labelId}>계정과목</label>
                <AccountCombobox
                  entries={registry.entries}
                  value={selectedId}
                  onChange={accountId => setSelections(current => ({ ...current, [item.txn_id]: accountId }))}
                  disabled={!assignmentEnabled || isPending}
                  labelledBy={labelId}
                />
                <fieldset disabled={!assignmentEnabled || isPending}>
                  <legend>적용 범위</legend>
                  <label><input type="radio" name={`scope-${item.txn_id}`} checked={(scopes[item.txn_id] ?? 'THIS_ONLY') === 'THIS_ONLY'} onChange={() => setScopes(current => ({ ...current, [item.txn_id]: 'THIS_ONLY' }))} />이번 거래만</label>
                  <label><input type="radio" name={`scope-${item.txn_id}`} checked={scopes[item.txn_id] === 'SAME_VENDOR_FUTURE'} disabled={!ruleEnabled} onChange={() => setScopes(current => ({ ...current, [item.txn_id]: 'SAME_VENDOR_FUTURE' }))} />같은 거래처의 다음 거래에도 제안</label>
                </fieldset>
                <button
                  type="button"
                  className="button-primary"
                  disabled={!assignmentEnabled || !selectedId || pendingTxn !== null}
                  onClick={() => void submit(item)}
                >
                  {isPending ? '저장 중' : '확인 후 저장'}
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {nextCursor && <button type="button" className="review-load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? '불러오는 중' : '거래 더 보기'}</button>}
      {conflict && <RuleConflictDialog problem={conflict.problem} pending={pendingTxn === conflict.txnId} onDecision={decision => void resolveConflict(decision)} onCancel={() => setConflict(null)} />}
      {rulesOpen && <LearnedRuleSettings onClose={() => setRulesOpen(false)} />}
    </section>
  );
}
