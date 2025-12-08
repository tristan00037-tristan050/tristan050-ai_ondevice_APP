/**
 * 회계 파일럿 데모 페이지
 * BFF 연결 시도, 실패 시 Mock 데이터 표시
 * 
 * @module ops-console/pages/demo/AccountingDemo
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const baseUrl = import.meta.env.VITE_BFF_URL || 'http://localhost:8081';

// Mock 데이터
const MOCK_SUMMARY = {
  approvals: { approved: 3, rejected: 1 },
  exports: { total: 2, failed: 0, expired: 0 },
  recon: { open: 1 },
  errors: { err5xx: 0 },
};

const MOCK_AUDIT_EVENTS = [
  { id: '1', action: 'approval_apply', subject_type: 'posting', subject_id: 'p1', ts: new Date().toISOString(), payload: { top1_selected: true, selected_rank: 1 } },
  { id: '2', action: 'approval_apply', subject_type: 'posting', subject_id: 'p2', ts: new Date().toISOString(), payload: { top1_selected: false, selected_rank: 2 } },
  { id: '3', action: 'manual_review_request', subject_type: 'posting', subject_id: 'p3', ts: new Date().toISOString(), payload: { reason_code: 'HIGH_VALUE', amount: 50000, currency: 'KRW' } },
  { id: '4', action: 'external_sync_success', subject_type: 'source', subject_id: 'bank-sbx', ts: new Date().toISOString(), payload: { source: 'bank-sbx', items: 10 } },
  { id: '5', action: 'approval_apply', subject_type: 'posting', subject_id: 'p4', ts: new Date().toISOString(), payload: { top1_selected: true, selected_rank: 1 } },
];

const MOCK_EXPORT_JOBS = [
  { jobId: 'export-1', status: 'completed', createdAt: new Date().toISOString(), reportCount: 5 },
  { jobId: 'export-2', status: 'pending', createdAt: new Date().toISOString(), reportCount: 0 },
];

const MOCK_RECON_SESSIONS = [
  { sessionId: 'recon-1', status: 'open', createdAt: new Date().toISOString(), matchedCount: 3, unmatchedCount: 2 },
];

// 파일럿 지표 Mock 데이터
const MOCK_PILOT_METRICS = {
  top1_accuracy: 0.67,  // 67%
  top5_accuracy: 1.0,   // 100%
  manual_review_ratio: 0.5,  // 50%
  sample: true,
};

// Risk Monitor Mock 데이터
const MOCK_HIGH_RISK = [
  {
    posting_id: 'p-high-1',
    level: 'HIGH',
    score: 90,
    reasons: ['HIGH_VALUE'],
    created_at: new Date().toISOString(),
  },
  {
    posting_id: 'p-high-2',
    level: 'HIGH',
    score: 85,
    reasons: ['HIGH_VALUE', 'LOW_CONFIDENCE'],
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
];

type SummaryData = typeof MOCK_SUMMARY;
type AuditEvent = typeof MOCK_AUDIT_EVENTS[0];
type ExportJob = typeof MOCK_EXPORT_JOBS[0];
type ReconSession = typeof MOCK_RECON_SESSIONS[0];
type PilotMetrics = typeof MOCK_PILOT_METRICS;

async function fetchSummary(): Promise<SummaryData> {
  try {
    const res = await fetch(`${baseUrl}/v1/accounting/os/summary`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': 'admin',
      },
    });
    if (!res.ok) throw new Error('bff error');
    return await res.json();
  } catch {
    return MOCK_SUMMARY;
  }
}

async function fetchAuditEvents(): Promise<AuditEvent[]> {
  try {
    const res = await fetch(`${baseUrl}/v1/accounting/audit?limit=10`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': 'admin',
      },
    });
    if (!res.ok) throw new Error('bff error');
    const data = await res.json();
    return data.events || [];
  } catch {
    return MOCK_AUDIT_EVENTS;
  }
}

async function fetchPilotMetrics(): Promise<PilotMetrics> {
  try {
    // TODO: 나중에 /v1/accounting/os/metrics/pilot 엔드포인트로 교체
    const res = await fetch(`${baseUrl}/v1/accounting/os/metrics/pilot`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': 'admin',
      },
    });
    if (!res.ok) throw new Error('bff error');
    return await res.json();
  } catch {
    // BFF 연결 실패 시 Mock 데이터 반환
    return MOCK_PILOT_METRICS;
  }
}

async function fetchHighRisk(): Promise<any[]> {
  try {
    const res = await fetch(`${baseUrl}/v1/accounting/risk/high?limit=50`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': 'admin',
        'X-Api-Key': 'collector-key:operator',
      },
    });
    if (!res.ok) throw new Error('bff error');
    const data = await res.json();
    return data.items || [];
  } catch {
    // BFF 연결 실패 시 Mock 데이터 반환
    return MOCK_HIGH_RISK;
  }
}

export default function AccountingDemo() {
  // OS 역할 (환경변수에서 읽기)
  const osRole = (import.meta.env.VITE_OS_ROLE || 'operator') as 'operator' | 'auditor' | 'admin';
  const isOperator = osRole === 'operator';
  const isAuditor = osRole === 'auditor' || osRole === 'admin';
  
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [pilotMetrics, setPilotMetrics] = useState<PilotMetrics | null>(null);
  const [highRiskList, setHighRiskList] = useState<any[]>([]);
  const [isMock, setIsMock] = useState(false);
  const [isSampleData, setIsSampleData] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [summaryData, auditData, metricsData, riskData] = await Promise.all([
        fetchSummary(),
        fetchAuditEvents(),
        fetchPilotMetrics(),
        fetchHighRisk(),
      ]);
      setSummary(summaryData);
      setAuditEvents(auditData);
      setPilotMetrics(metricsData);
      setHighRiskList(riskData);
      setIsMock(summaryData === MOCK_SUMMARY || auditData === MOCK_AUDIT_EVENTS);
      setIsSampleData(metricsData?.sample === true || riskData === MOCK_HIGH_RISK);
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">회계 파일럿 데모</h1>
        {isSampleData && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
            ⚠️ 샘플 데이터입니다
          </div>
        )}
        {isMock && !isSampleData && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
            ⚠️ 샘플 데이터 모드 (BFF 연결 실패 또는 서버 미실행)
          </div>
        )}
      </div>

      {/* 파일럿 지표 카드 */}
      {pilotMetrics && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-white p-6 rounded-lg shadow border-l-4 border-blue-500">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-500">Top-1 정확도</h3>
              {isSampleData && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">샘플</span>
              )}
            </div>
            <p className="text-3xl font-bold text-blue-600">
              {(pilotMetrics.top1_accuracy * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-gray-500 mt-2">추천 1위 선택 비율</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow border-l-4 border-green-500">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-500">Top-5 정확도</h3>
              {isSampleData && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">샘플</span>
              )}
            </div>
            <p className="text-3xl font-bold text-green-600">
              {(pilotMetrics.top5_accuracy * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-gray-500 mt-2">추천 상위 5개 내 선택 비율</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow border-l-4 border-orange-500">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-500">Manual Review 비율</h3>
              {isSampleData && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">샘플</span>
              )}
            </div>
            <p className="text-3xl font-bold text-orange-600">
              {(pilotMetrics.manual_review_ratio * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-gray-500 mt-2">수동 검토 요청 비율</p>
          </div>
        </div>
      )}

      {/* 요약 카드 */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-medium text-gray-500 mb-2">오늘 추천 수</h3>
            <p className="text-2xl font-bold">{summary.approvals.approved + summary.approvals.rejected}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-medium text-gray-500 mb-2">승인 수</h3>
            <p className="text-2xl font-bold text-green-600">{summary.approvals.approved}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-medium text-gray-500 mb-2">수동 검토 수</h3>
            <p className="text-2xl font-bold text-orange-600">{summary.approvals.rejected}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-medium text-gray-500 mb-2">Export Jobs</h3>
            <p className="text-2xl font-bold">{summary.exports.total}</p>
            <p className="text-sm text-gray-500">실패: {summary.exports.failed}</p>
          </div>
        </div>
      )}

      {/* 최근 Audit 이벤트 테이블 */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <h2 className="text-xl font-semibold">최근 Audit 이벤트 (최근 10건)</h2>
          {isOperator && (
            <span className="text-sm text-gray-500 bg-yellow-50 px-3 py-1 rounded">
              읽기 전용 (auditor 이상 권한 필요)
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Subject</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Payload</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">시간</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {auditEvents.map((event) => (
                <tr key={event.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{event.action}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {event.subject_type}:{event.subject_id}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-w-md">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(event.ts).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Export Jobs 요약 */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Export Jobs 요약</h2>
        </div>
        <div className="px-6 py-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {MOCK_EXPORT_JOBS.map((job) => (
              <div key={job.jobId} className="border rounded p-4">
                <div className="font-medium">{job.jobId}</div>
                <div className="text-sm text-gray-500">상태: {job.status}</div>
                <div className="text-sm text-gray-500">리포트 수: {job.reportCount}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recon Sessions 요약 */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Recon Sessions 요약</h2>
        </div>
        <div className="px-6 py-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {MOCK_RECON_SESSIONS.map((session) => (
              <div key={session.sessionId} className="border rounded p-4">
                <div className="font-medium">{session.sessionId}</div>
                <div className="text-sm text-gray-500">상태: {session.status}</div>
                <div className="text-sm text-gray-500">매칭: {session.matchedCount} / 미매칭: {session.unmatchedCount}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Risk Monitor 패널 */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <h2 className="text-xl font-semibold">Risk Monitor</h2>
          {isSampleData && (
            <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">샘플 데이터</span>
          )}
        </div>
        <div className="px-6 py-4">
          {/* 상단 카드 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">최근 24시간 HIGH 거래 수</h3>
              <p className="text-2xl font-bold text-red-600">{highRiskList.length}</p>
              {highRiskList.length > 0 && (
                <Link 
                  to="/manual-review" 
                  className="text-sm text-red-600 hover:text-red-800 mt-2 inline-block"
                >
                  → Manual Review Workbench에서 확인
                </Link>
              )}
            </div>
            <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">HIGH 중 아직 승인되지 않은 수</h3>
              <p className="text-2xl font-bold text-orange-600">
                {highRiskList.filter((r: any) => !r.approved).length}
              </p>
            </div>
          </div>
          
          {/* 하단 테이블 */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">날짜/시간</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Posting ID</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk 레벨</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">점수</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">이유</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">상태</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {highRiskList.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-4 text-center text-sm text-gray-500">
                      최근 HIGH 레벨 거래가 없습니다.
                    </td>
                  </tr>
                ) : (
                  highRiskList.map((risk: any) => (
                    <tr key={risk.posting_id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(risk.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{risk.posting_id}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs font-semibold rounded ${
                          risk.level === 'HIGH' 
                            ? 'bg-red-100 text-red-800' 
                            : risk.level === 'MEDIUM'
                            ? 'bg-orange-100 text-orange-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {risk.level}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{risk.score}</td>
                      <td className="px-6 py-4 text-sm text-gray-500">
                        {risk.reasons?.join(', ') || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {risk.approved ? '승인됨' : '대기'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          
          {isOperator && (
            <div className="mt-4 text-sm text-gray-500 bg-yellow-50 px-4 py-2 rounded">
              읽기 전용 (auditor 이상 권한 필요)
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

