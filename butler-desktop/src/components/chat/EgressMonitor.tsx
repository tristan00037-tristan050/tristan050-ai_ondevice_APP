import React, { useEffect, useState } from 'react';
import { SIDECAR_BASE } from '../../constants';

interface EgressReport {
  schema_version: string;
  task_id: string;
  mode: string;
  raw_file_sent_external: boolean;
  raw_text_logged: boolean;
  egress_bytes_total: number;
  dns_requests: number;
  http_requests: number;
  https_requests: number;
  telemetry_enabled: boolean;
  crash_report_enabled: boolean;
  update_check_enabled: boolean;
  verdict: 'PASS' | 'FAIL';
  generated_at: string;
}

interface EgressMonitorProps {
  onClose: () => void;
}

function downloadJson(data: object, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <tr>
      <td style={{ padding: '4px 8px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>{label}</td>
      <td
        data-testid={`egress-${label.toLowerCase().replace(/\s+/g, '-')}`}
        style={{
          padding: '4px 8px',
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          color: value ? 'var(--color-error)' : 'var(--color-success)',
        }}
      >
        {value ? '⚠️ 활성' : '✓ 비활성'}
      </td>
    </tr>
  );
}

export function EgressMonitor({ onClose }: EgressMonitorProps) {
  const [report, setReport] = useState<EgressReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${SIDECAR_BASE}/api/egress/report`)
      .then(r => r.json() as Promise<EgressReport>)
      .then(data => {
        setReport(data);
        setLoading(false);
      })
      .catch(err => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  const handleDownload = () => {
    if (!report) return;
    const filename = `butler_egress_report_${report.task_id}.json`;
    downloadJson(report, filename);
  };

  return (
    <>
      {/* Overlay backdrop */}
      <div
        data-testid="egress-monitor-backdrop"
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.3)',
          zIndex: 200,
        }}
      />

      {/* Modal panel */}
      <div
        data-testid="egress-monitor-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Egress Monitor"
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 201,
          background: 'var(--color-bg-input)',
          borderRadius: 12,
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
          padding: 'var(--space-6)',
          minWidth: 360,
          maxWidth: 480,
          width: '90vw',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
            🔒 Egress Monitor
          </h2>
          <button
            data-testid="egress-monitor-close"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 18,
              color: 'var(--color-text-secondary)',
              lineHeight: 1,
            }}
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        {loading && (
          <p data-testid="egress-monitor-loading" style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
            데이터 로딩 중...
          </p>
        )}

        {error && (
          <p data-testid="egress-monitor-error" style={{ color: 'var(--color-error)', fontSize: 'var(--text-sm)' }}>
            불러오기 실패: {error}
          </p>
        )}

        {report && !loading && (
          <>
            {/* Verdict badge */}
            <div style={{ marginBottom: 'var(--space-4)', textAlign: 'center' }}>
              <span
                data-testid="egress-monitor-verdict"
                style={{
                  padding: '4px 16px',
                  borderRadius: 99,
                  background: report.verdict === 'PASS' ? 'rgba(15,123,15,0.12)' : 'rgba(185,28,28,0.12)',
                  color: report.verdict === 'PASS' ? 'var(--color-success)' : 'var(--color-error)',
                  fontWeight: 700,
                  fontSize: 'var(--text-sm)',
                }}
              >
                {report.verdict === 'PASS' ? '✓ PASS — 외부 송신 없음' : '⚠️ FAIL — 외부 송신 감지'}
              </span>
            </div>

            {/* Data table */}
            <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 'var(--space-4)' }}>
              <tbody>
                <tr>
                  <td style={{ padding: '4px 8px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>모드</td>
                  <td data-testid="egress-monitor-mode" style={{ padding: '4px 8px', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                    {report.mode === 'local_only' ? '🏠 Local-only' : report.mode}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '4px 8px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>외부 송신 바이트</td>
                  <td data-testid="egress-monitor-bytes" style={{ padding: '4px 8px', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                    {report.egress_bytes_total} bytes
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '4px 8px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>DNS 요청</td>
                  <td style={{ padding: '4px 8px', fontSize: 'var(--text-sm)' }}>{report.dns_requests}</td>
                </tr>
                <BoolRow label="원본 파일 외부 전송" value={report.raw_file_sent_external} />
                <BoolRow label="원문 로깅" value={report.raw_text_logged} />
                <BoolRow label="원격 측정" value={report.telemetry_enabled} />
                <BoolRow label="충돌 보고" value={report.crash_report_enabled} />
                <BoolRow label="업데이트 확인" value={report.update_check_enabled} />
              </tbody>
            </table>

            <p style={{ margin: '0 0 var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
              생성: {new Date(report.generated_at).toLocaleString('ko-KR')}
            </p>

            <button
              data-testid="egress-monitor-download"
              onClick={handleDownload}
              style={{
                width: '100%',
                padding: 'var(--space-2) var(--space-4)',
                background: 'var(--color-brand-primary)',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                fontWeight: 600,
              }}
            >
              📥 Local-only Report 다운로드
            </button>
          </>
        )}
      </div>
    </>
  );
}
