/**
 * Manual Review Workbench 페이지
 * 
 * auditor/리스크 담당자가 수동 검토 큐를 보고, 각 거래를 승인/거절하는 화면
 * 
 * @module ops-console/pages/manual-review/ManualReviewPage
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const baseUrl = import.meta.env.VITE_BFF_URL || 'http://localhost:8081';

// OS 역할 (환경변수에서 읽기)
const osRole = (import.meta.env.VITE_OS_ROLE || 'operator') as 'operator' | 'auditor' | 'admin';
const isOperator = osRole === 'operator';
const isAuditor = osRole === 'auditor' || osRole === 'admin';

// Mock 데이터
const MOCK_MANUAL_REVIEW_ITEMS = [
  {
    id: 1,
    posting_id: 'p-high-1',
    risk_level: 'HIGH',
    reasons: ['HIGH_VALUE'],
    source: 'HUD',
    status: 'PENDING',
    assignee: null,
    note: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 2,
    posting_id: 'p-high-2',
    risk_level: 'HIGH',
    reasons: ['HIGH_VALUE', 'LOW_CONFIDENCE'],
    source: 'HUD',
    status: 'PENDING',
    assignee: null,
    note: null,
    created_at: new Date(Date.now() - 3600000).toISOString(),
    updated_at: new Date(Date.now() - 3600000).toISOString(),
  },
];

type ManualReviewItem = typeof MOCK_MANUAL_REVIEW_ITEMS[0];

async function fetchManualReview(status?: string): Promise<ManualReviewItem[]> {
  try {
    const url = status 
      ? `${baseUrl}/v1/accounting/manual-review?status=${status}`
      : `${baseUrl}/v1/accounting/manual-review`;
    
    const res = await fetch(url, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': osRole,
        'X-Api-Key': 'collector-key:operator',
      },
    });
    
    if (!res.ok) throw new Error('bff error');
    const data = await res.json();
    return data.items || [];
  } catch {
    // BFF 연결 실패 시 Mock 데이터 반환
    return MOCK_MANUAL_REVIEW_ITEMS;
  }
}

async function resolveManualReview(id: number, status: 'APPROVED' | 'REJECTED', note?: string): Promise<void> {
  const res = await fetch(`${baseUrl}/v1/accounting/manual-review/${id}/resolve`, {
    method: 'POST',
    headers: {
      'X-Tenant': 'default',
      'X-User-Id': 'ops-demo',
      'X-User-Role': osRole,
      'X-Api-Key': 'collector-key:auditor',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ status, note }),
  });
  
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }
}

export default function ManualReviewPage() {
  const [items, setItems] = useState<ManualReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('PENDING');
  const [isMock, setIsMock] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const data = await fetchManualReview(statusFilter);
      setItems(data);
      setIsMock(data === MOCK_MANUAL_REVIEW_ITEMS);
      setLoading(false);
    }
    load();
  }, [statusFilter]);

  const handleResolve = async (id: number, status: 'APPROVED' | 'REJECTED') => {
    if (!isAuditor) return;
    
    const note = status === 'REJECTED' 
      ? prompt('거절 사유를 입력하세요:') || undefined
      : undefined;
    
    try {
      await resolveManualReview(id, status, note);
      // 목록 새로고침
      const data = await fetchManualReview(statusFilter);
      setItems(data);
    } catch (error: any) {
      alert(`처리 실패: ${error.message}`);
    }
  };

  // 통계 계산
  const pendingCount = items.filter(i => i.status === 'PENDING').length;
  const inReviewCount = items.filter(i => i.status === 'IN_REVIEW').length;
  const todayResolved = items.filter(i => {
    const date = new Date(i.updated_at);
    const today = new Date();
    return (i.status === 'APPROVED' || i.status === 'REJECTED') &&
           date.toDateString() === today.toDateString();
  }).length;

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
        <h1 className="text-3xl font-bold mb-2">Manual Review Workbench</h1>
        {isMock && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
            ⚠️ 샘플 데이터 모드 (BFF 연결 실패 또는 서버 미실행)
          </div>
        )}
        {isOperator && (
          <div className="bg-blue-100 border border-blue-400 text-blue-700 px-4 py-3 rounded mb-4">
            ℹ️ 읽기 전용 모드 (auditor 이상 권한 필요)
          </div>
        )}
      </div>

      {/* 상단 요약 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-yellow-500">
          <h3 className="text-sm font-medium text-gray-500 mb-2">대기(PENDING)</h3>
          <p className="text-3xl font-bold text-yellow-600">{pendingCount}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-blue-500">
          <h3 className="text-sm font-medium text-gray-500 mb-2">검토 중(IN_REVIEW)</h3>
          <p className="text-3xl font-bold text-blue-600">{inReviewCount}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-green-500">
          <h3 className="text-sm font-medium text-gray-500 mb-2">오늘 처리 건수</h3>
          <p className="text-3xl font-bold text-green-600">{todayResolved}</p>
        </div>
      </div>

      {/* 필터 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">상태 필터:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">전체</option>
          <option value="PENDING">PENDING</option>
          <option value="IN_REVIEW">IN_REVIEW</option>
          <option value="APPROVED">APPROVED</option>
          <option value="REJECTED">REJECTED</option>
        </select>
      </div>

      {/* 큐 테이블 */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Manual Review Queue</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">생성일시</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Posting ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk 레벨</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">이유</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">요청자</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">현재 상태</th>
                {isAuditor && (
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">액션</th>
                )}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={isAuditor ? 7 : 6} className="px-6 py-4 text-center text-sm text-gray-500">
                    수동 검토 항목이 없습니다.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <Link 
                        to={`/demo/accounting`}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        {item.posting_id}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 text-xs font-semibold rounded ${
                        item.risk_level === 'HIGH' 
                          ? 'bg-red-100 text-red-800' 
                          : item.risk_level === 'MEDIUM'
                          ? 'bg-orange-100 text-orange-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        {item.risk_level}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {item.reasons?.slice(0, 2).join(', ') || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {item.source}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 text-xs font-semibold rounded ${
                        item.status === 'PENDING'
                          ? 'bg-yellow-100 text-yellow-800'
                          : item.status === 'IN_REVIEW'
                          ? 'bg-blue-100 text-blue-800'
                          : item.status === 'APPROVED'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {item.status}
                      </span>
                    </td>
                    {isAuditor && (
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        {item.status === 'PENDING' || item.status === 'IN_REVIEW' ? (
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleResolve(item.id, 'APPROVED')}
                              className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                            >
                              승인
                            </button>
                            <button
                              onClick={() => handleResolve(item.id, 'REJECTED')}
                              className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700"
                            >
                              거절
                            </button>
                          </div>
                        ) : (
                          <span className="text-gray-400">처리 완료</span>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

