import React from 'react';
import type { Box3RealVerdictResponse } from '../../lib/box3/box3RealEnablement';

export function Box3RealEnablementPanel({ verdict }: { verdict: Box3RealVerdictResponse | null }) {
  if (!verdict) {
    return <section aria-label="Box 3 real enablement status"><p>박스 3 real 상태 대기</p></section>;
  }
  const statusLabel = verdict.real_claim_allowed ? 'REAL_APPROVED' : verdict.status;
  return (
    <section aria-label="Box 3 real enablement status">
      <h3>박스 3 real 상태</h3>
      <p>상태: {statusLabel}</p>
      <p>fail_class: {verdict.fail_class ?? '없음'}</p>
      <p>real_claim_allowed: {String(verdict.real_claim_allowed)}</p>
      <p>human_approval_required: {String(verdict.human_approval_required)}</p>
      <p>원문 저장 0건</p>
      <p>외부 송신 0건</p>
      <dl>
        <dt>unsupported_claim_rate</dt><dd>{verdict.metrics.unsupported_claim_rate.toFixed(3)}</dd>
        <dt>no_evidence_claim_rate</dt><dd>{verdict.metrics.no_evidence_claim_rate.toFixed(3)}</dd>
        <dt>citation_accuracy</dt><dd>{verdict.metrics.citation_accuracy.toFixed(3)}</dd>
      </dl>
      {verdict.draft_text ? <textarea readOnly value={verdict.draft_text} aria-label="박스 3 draft" /> : <p>발행 가능한 draft 없음</p>}
      <h4>citations</h4>
      <ul>
        {verdict.citations.map((citation, index) => (
          <li key={`${citation.evidence_digest}-${index}`}>{citation.source_digest} / {citation.evidence_kind}</li>
        ))}
      </ul>
    </section>
  );
}
