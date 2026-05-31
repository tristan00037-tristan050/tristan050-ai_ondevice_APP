import type { RouterDecisionV1 } from '../../lib/connect_loop/contracts';

interface SecurityBadgesProps {
  decision: RouterDecisionV1 | null;
  fallbackRequired: boolean;
  integrationMode: string | null;
  usageLogCount: number | null;
}

function badge(label: string, value: string): string {
  return `${label}: ${value}`;
}

export function SecurityBadges({
  decision,
  fallbackRequired,
  integrationMode,
  usageLogCount,
}: SecurityBadgesProps) {
  const entries = [
    '원문 미반출',
    '비로컬 전송 0',
    badge('정책', decision?.policy_precheck ?? '대기'),
    badge('대상', decision?.target_box_id ?? '대기'),
    fallbackRequired ? '안전 처리됨' : '직접 실행',
    badge('integration_mode', integrationMode ?? 'unknown'),
  ];
  if (usageLogCount !== null) {
    entries.push(`usage_log ${usageLogCount}건`);
  }

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
