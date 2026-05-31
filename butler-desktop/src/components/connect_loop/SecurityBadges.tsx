import type { RouterDecisionV1 } from '../../lib/connect_loop/contracts';
import type { BridgeStatus, UsageLogVerification } from '../../lib/connect_loop/client';

interface SecurityBadgesProps {
  decision: RouterDecisionV1 | null;
  fallbackRequired: boolean;
  integrationMode: string | null;
  usageLogCount: number | null;
  usageLogVerification?: UsageLogVerification;
  status?: BridgeStatus;
}

// Codex P2: 보안이 입증되지 않은 상태에서는 zero-leak 배지를 단정 표기하지 않는다(거짓 PASS 방지).
const UNVERIFIED_STATUSES = new Set<BridgeStatus>(['security_blocked', 'decision_invalid', 'endpoint_failed']);

function badge(label: string, value: string): string {
  return `${label}: ${value}`;
}

export function SecurityBadges({
  decision,
  fallbackRequired,
  integrationMode,
  usageLogCount,
  usageLogVerification = 'not_configured',
  status,
}: SecurityBadgesProps) {
  const securityVerified = status === undefined ? true : !UNVERIFIED_STATUSES.has(status);
  const entries = [
    // zero-leak 단정은 검증된 상태에서만. 미검증(차단/무효/실패)이면 명시적 미검증 배지.
    ...(securityVerified ? ['원문 미반출', '비로컬 전송 0'] : ['보안 미검증 — 결과 차단']),
    badge('정책', decision?.policy_precheck ?? '대기'),
    badge('대상', decision?.target_box_id ?? '대기'),
    fallbackRequired ? '안전 처리됨' : '직접 실행',
    badge('integration_mode', integrationMode ?? 'unknown'),
  ];
  if (usageLogCount !== null) {
    entries.push(`usage_log ${usageLogCount}건`);
  }
  // 거짓 PASS 금지: usage_log 독립 검증 상태를 명시(미구성은 not_configured).
  entries.push(badge('usage_log 검증', usageLogVerification));

  return (
    <div
      data-testid="connect-loop-security-badges"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        marginTop: 12,
      }}
    >
      {entries.map(entry => (
        <span
          key={entry}
          style={{
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 6,
            padding: '4px 8px',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-secondary)',
            background: 'var(--color-bg-app)',
          }}
        >
          {entry}
        </span>
      ))}
    </div>
  );
}
