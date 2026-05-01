import React, { useState } from 'react';
import type { EgressStats } from '../types';

interface EgressBadgeProps {
  stats?: Partial<EgressStats>;
  isBlocked?: boolean;
  isWorking?: boolean;
}

const DEFAULT_STATS: EgressStats = {
  task_id: '',
  mode: 'local_only',
  egress_bytes_total: 0,
  dns_requests: 0,
  http_requests: 0,
  https_requests: 0,
  telemetry_enabled: false,
  crash_report_enabled: false,
  update_check_enabled: false,
  raw_text_logged: false,
  input_digest16: 'sha256:0000000000000000',
  output_digest16: 'sha256:0000000000000000',
  verdict: 'PASS',
};

function downloadJson(data: object, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function EgressBadge({ stats: statsProp, isBlocked = false, isWorking = false }: EgressBadgeProps) {
  const [open, setOpen] = useState(false);
  const stats: EgressStats = { ...DEFAULT_STATS, ...statsProp };

  const badgeColor = isBlocked ? '#f5222d' : '#52c41a';
  const badgeText = isBlocked
    ? '⚠️ 외부 송신 차단됨'
    : isWorking
    ? `🔒 외부 송신 ${stats.egress_bytes_total} · 작업 중`
    : `🔒 외부 송신 ${stats.egress_bytes_total} · Local-only Mode`;

  const handleDownload = () => {
    downloadJson({ schema_version: 'egress_report.v2', ...stats }, `egress_report_${Date.now()}.json`);
  };

  return (
    <div>
      <button
        data-testid="egress-badge"
        onClick={() => setOpen(o => !o)}
        style={{ background: badgeColor, color: '#fff', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer' }}
        aria-expanded={open}
      >
        {badgeText}
      </button>

      {open && (
        <div data-testid="egress-panel" style={{ marginTop: 8, padding: 16, border: '1px solid #ddd', borderRadius: 8 }}>
          <h3 style={{ margin: '0 0 8px' }}>Egress Monitor</h3>
          <dl>
            <dt>Mode</dt><dd data-testid="egress-mode">{stats.mode}</dd>
            <dt>Egress bytes total</dt><dd data-testid="egress-bytes">{stats.egress_bytes_total}</dd>
            <dt>DNS requests</dt><dd>{stats.dns_requests}</dd>
            <dt>HTTP requests</dt><dd>{stats.http_requests}</dd>
            <dt>HTTPS requests</dt><dd>{stats.https_requests}</dd>
            <dt>Telemetry</dt><dd>{stats.telemetry_enabled ? 'enabled' : 'disabled'}</dd>
            <dt>Raw text logged</dt><dd>{String(stats.raw_text_logged)}</dd>
            <dt>Verdict</dt><dd data-testid="egress-verdict">{stats.verdict}</dd>
          </dl>
          <button data-testid="download-btn" onClick={handleDownload}>
            Egress Report 다운로드 (.json)
          </button>
        </div>
      )}
    </div>
  );
}
