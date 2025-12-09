/**
 * OS Dashboard 페이지
 * 
 * 회계·리스크·운영팀이 AI 온디바이스 OS의 현재 상태를 한눈에 모니터링하는 화면
 * 
 * @module ops-console/pages/os/OsDashboard
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const baseUrl = import.meta.env.VITE_BFF_URL || 'http://localhost:8081';
const osRole = (import.meta.env.VITE_OS_ROLE || 'operator') as 'operator' | 'auditor' | 'admin';

type EngineMode = 'mock' | 'rule' | 'local-llm' | 'remote';

type EngineSection = {
  primary_mode: EngineMode | null;
  counts: Record<EngineMode, number>;
};

type DashboardData = {
  window: {
    from: string;
    to: string;
  };
  pilot: {
    suggest_calls: number;
    top1_accuracy: number;
    manual_review_rate: number;
  };
  risk: {
    high_risk_24h: number;
    medium_risk_24h: number;
    low_risk_24h: number;
    manual_review_pending: number;
  };
  health?: {
    success_rate_5m: number;
    error_rate_5m: number;
    p95_latency_5m: number | null;
  };
  queue: {
    offline_queue_backlog: number;
  };
  engine?: EngineSection;
};

async function fetchDashboard(): Promise<DashboardData | null> {
  try {
    const res = await fetch(`${baseUrl}/v1/accounting/os/dashboard`, {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops-demo',
        'X-User-Role': osRole,
        'X-Api-Key': 'collector-key:operator',
      },
    });
    
    if (!res.ok) throw new Error('bff error');
    return await res.json();
  } catch {
    // BFF 연결 실패 시 null 반환
    return null;
  }
}

export default function OsDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [isMock, setIsMock] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const result = await fetchDashboard();
      setData(result);
      setIsMock(result === null);
      setLoading(false);
    }
    load();
    
    // 30초마다 자동 새로고침
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">로딩 중...</div>
      </div>
    );
  }

  // Mock 데이터 (BFF 연결 실패 시)
  const mockData: DashboardData = {
    window: {
      from: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      to: new Date().toISOString(),
    },
    pilot: {
      suggest_calls: 123,
      top1_accuracy: 0.87,
      manual_review_rate: 0.18,
    },
    risk: {
      high_risk_24h: 7,
      medium_risk_24h: 12,
      low_risk_24h: 104,
      manual_review_pending: 3,
    },
    queue: {
      offline_queue_backlog: 0,
    },
    engine: {
      primary_mode: 'local-llm',
      counts: {
        mock: 0,
        rule: 12,
        'local-llm': 34,
        remote: 0,
      },
    },
  };

  const displayData = data || mockData;
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true' || isMock;

  // 엔진 모드 카드 렌더링 함수 (R8-S2)
  function renderEngineModeCard(engine?: EngineSection) {
    if (!engine) {
      return (
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-gray-400">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            엔진 모드
            <span className="ml-2 text-gray-400 cursor-help" title="현재 사용 중인 엔진 모드 정보입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-sm text-gray-500">데이터가 아직 수집되지 않았습니다.</p>
        </div>
      );
    }

    const labelMap: Record<EngineMode, string> = {
      mock: 'Mock (데모)',
      rule: '규칙 기반',
      'local-llm': 'On-device LLM',
      remote: '원격 LLM',
    };

    const primaryLabel = engine.primary_mode != null ? labelMap[engine.primary_mode] : '없음';
    const totalCount = Object.values(engine.counts).reduce((sum, count) => sum + count, 0);

    return (
      <div className="bg-white p-6 rounded-lg shadow border-l-4 border-purple-500">
        <h3 className="text-sm font-medium text-gray-500 mb-2">
          엔진 모드
          <span className="ml-2 text-gray-400 cursor-help" title="지난 24시간 기준 엔진 사용 분포와 주요 엔진 모드입니다.">
            ⓘ
          </span>
        </h3>
        <p className="text-lg font-semibold text-purple-600 mb-2">
          주요 엔진: {primaryLabel}
        </p>
        {totalCount > 0 ? (
          <div className="text-xs text-gray-600 space-y-1">
            <div>분포: rule {engine.counts.rule} • local-llm {engine.counts['local-llm']} • mock {engine.counts.mock} • remote {engine.counts.remote}</div>
            <div className="text-gray-500">총 {totalCount}건</div>
          </div>
        ) : (
          <p className="text-xs text-gray-500">아직 데이터가 없습니다.</p>
        )}
        {isDemoMode && (
          <p className="text-xs text-blue-600 mt-2">
            현재 데모 환경에서는 엔진 모드 데이터가 샘플 기반으로 표시됩니다.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">OS Dashboard</h1>
        <p className="text-gray-600">AI 온디바이스 OS 전체 건강 상태 모니터링</p>
        {isDemoMode && (
          <div className="bg-blue-100 border border-blue-400 text-blue-700 px-4 py-3 rounded mt-4">
            <div className="font-semibold mb-1">데모/파일럿 모드</div>
            <div className="text-sm">
              현재 대시보드는 데모/파일럿 데이터 기준으로 동작합니다.
              <br />
              실제 도입 시에는 귀사 ERP/회계 시스템과 연동됩니다.
            </div>
          </div>
        )}
        {isMock && !isDemoMode && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mt-4">
            ⚠️ 샘플 데이터 모드 (BFF 연결 실패 또는 서버 미실행)
          </div>
        )}
      </div>

      {/* 첫 줄 - 정확도 & 품질 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-blue-500 relative group">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            지난 24시간 Top-1 정확도
            <span className="ml-2 text-gray-400 cursor-help" title="AI 추천 중 1순위가 실제 선택과 일치한 비율입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-3xl font-bold text-blue-600">
            {Math.round(displayData.pilot.top1_accuracy * 100)}%
          </p>
          <p className="text-xs text-gray-500 mt-2">
            {displayData.pilot.suggest_calls}건 추천 중
          </p>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-orange-500 relative group">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            지난 24시간 수동 검토 비율
            <span className="ml-2 text-gray-400 cursor-help" title="전체 추천 중 수동 검토로 넘어간 비율입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-3xl font-bold text-orange-600">
            {Math.round(displayData.pilot.manual_review_rate * 100)}%
          </p>
          <p className="text-xs text-gray-500 mt-2">
            {displayData.pilot.manual_review_requests || 0}건 요청
          </p>
        </div>
      </div>

      {/* 둘째 줄 - 안정성 & 리스크 & 엔진 모드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-green-500 relative group">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            최근 5분간 BFF 성공률
            <span className="ml-2 text-gray-400 cursor-help" title="BFF API 호출 중 성공한 비율입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-3xl font-bold text-green-600">
            {displayData.health?.success_rate_5m ? Math.round(displayData.health.success_rate_5m * 100) : 100}%
          </p>
          {displayData.health?.p95_latency_5m && (
            <p className="text-xs text-gray-500 mt-2">
              P95 지연: {displayData.health.p95_latency_5m}ms
            </p>
          )}
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-red-500 relative group">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            지난 24시간 HIGH Risk 거래 수
            <span className="ml-2 text-gray-400 cursor-help" title="최근 24시간 동안 발생한 HIGH Risk 거래 수입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-3xl font-bold text-red-600">{displayData.risk.high_risk_24h}</p>
          <Link 
            to="/manual-review" 
            className="text-xs text-red-600 hover:text-red-800 mt-2 inline-block"
          >
            → Manual Review에서 확인
          </Link>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-yellow-500 relative group">
          <h3 className="text-sm font-medium text-gray-500 mb-2">
            Manual Review 대기 건 수
            <span className="ml-2 text-gray-400 cursor-help" title="현재 수동 검토 대기 중인 건 수입니다.">
              ⓘ
            </span>
          </h3>
          <p className="text-3xl font-bold text-yellow-600">
            {displayData.risk.manual_review_pending}
          </p>
          <Link 
            to="/manual-review" 
            className="text-xs text-yellow-600 hover:text-yellow-800 mt-2 inline-block"
          >
            → Workbench에서 처리
          </Link>
        </div>
        
        {/* 엔진 모드 카드 (R8-S2) */}
        {renderEngineModeCard(displayData.engine)}
      </div>

      {/* 가운데 섹션: Risk 분포 */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">Risk 분포 (최근 24시간)</h2>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{displayData.risk.high_risk_24h}</div>
              <div className="text-sm text-gray-500">HIGH</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">{displayData.risk.medium_risk_24h}</div>
              <div className="text-sm text-gray-500">MEDIUM</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-600">{displayData.risk.low_risk_24h}</div>
              <div className="text-sm text-gray-500">LOW</div>
            </div>
          </div>
        </div>
      </div>

      {/* 하단 섹션: 주요 이벤트 */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">오늘의 주요 이벤트</h2>
        </div>
        <div className="p-6">
          <div className="space-y-4">
            {displayData.risk.high_risk_24h > 0 && (
              <div className="flex items-center justify-between p-4 bg-red-50 rounded border border-red-200">
                <div>
                  <div className="font-semibold text-red-800">
                    HIGH Risk 거래 {displayData.risk.high_risk_24h}건 발생
                  </div>
                  <div className="text-sm text-red-600 mt-1">
                    수동 검토 권장
                  </div>
                </div>
                <Link
                  to="/manual-review"
                  className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                >
                  확인
                </Link>
              </div>
            )}
            
            {displayData.risk.manual_review_pending > 0 && (
              <div className="flex items-center justify-between p-4 bg-yellow-50 rounded border border-yellow-200">
                <div>
                  <div className="font-semibold text-yellow-800">
                    Manual Review 대기 {displayData.risk.manual_review_pending}건
                  </div>
                  <div className="text-sm text-yellow-600 mt-1">
                    검토 필요
                  </div>
                </div>
                <Link
                  to="/manual-review"
                  className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 text-sm"
                >
                  처리
                </Link>
              </div>
            )}
            
            {displayData.risk.high_risk_24h === 0 && displayData.risk.manual_review_pending === 0 && (
              <div className="text-center text-gray-500 py-8">
                오늘 발생한 주요 이벤트가 없습니다.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* CS 모듈 (준비 중) */}
      <div className="bg-white rounded-lg shadow p-6 mt-8">
        <h2 className="text-xl font-semibold mb-4">CS 모듈 (준비 중)</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-50 p-6 rounded-lg border-l-4 border-gray-400">
            <h3 className="text-sm font-medium text-gray-500 mb-2">
              CS 티켓 처리 현황 (준비 중)
              <span className="ml-2 text-gray-400 cursor-help" title="CS 도메인용 지표 슬롯입니다. R8-S1에서는 실제 데이터 연동 없이 자리만 구성합니다.">
                ⓘ
              </span>
            </h3>
            <p className="text-3xl font-bold text-gray-400">--</p>
            <p className="text-xs text-gray-500 mt-2">준비 중</p>
          </div>
          <div className="bg-gray-50 p-6 rounded-lg border-l-4 border-gray-400">
            <h3 className="text-sm font-medium text-gray-500 mb-2">
              CS 응답 품질 지표 (준비 중)
              <span className="ml-2 text-gray-400 cursor-help" title="향후 온디바이스 LLM 기반 CS 응답 품질 지표가 들어갈 자리입니다.">
                ⓘ
              </span>
            </h3>
            <p className="text-3xl font-bold text-gray-400">--</p>
            <p className="text-xs text-gray-500 mt-2">준비 중</p>
          </div>
        </div>
      </div>

      {/* Demo 플로우 링크 */}
      <div className="bg-white rounded-lg shadow p-6 mt-8">
        <h2 className="text-xl font-semibold mb-4">Demo 플로우</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/demo/accounting"
            className="px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-center font-medium transition-colors"
          >
            Accounting Demo 열기
          </Link>
          <Link
            to="/manual-review"
            className="px-6 py-4 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-center font-medium transition-colors"
          >
            Manual Review Workbench 열기
          </Link>
          <Link
            to="/demo/accounting"
            className="px-6 py-4 bg-red-600 text-white rounded-lg hover:bg-red-700 text-center font-medium transition-colors"
          >
            Risk Monitor 열기
          </Link>
        </div>
      </div>

      {/* 데이터 새로고침 정보 */}
      <div className="mt-4 text-center text-sm text-gray-500">
        데이터는 30초마다 자동으로 새로고침됩니다.
        <br />
        마지막 업데이트: {new Date(displayData.window.to).toLocaleString()}
      </div>
    </div>
  );
}

