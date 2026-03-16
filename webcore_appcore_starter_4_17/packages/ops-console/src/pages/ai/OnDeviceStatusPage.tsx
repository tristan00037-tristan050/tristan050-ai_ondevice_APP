/**
 * OnDeviceStatusPage.tsx
 * 온디바이스 AI 기기별 상태 대시보드
 * — 기기 등록 현황, 모델 로드 상태, 추론 성능, 이상 감지
 */

import React, { useState, useEffect } from 'react';

// ─── 타입 ─────────────────────────────────────────────────────────────────────

type DeviceStatus = 'online' | 'offline' | 'degraded' | 'updating';
type OS = 'Android' | 'iOS' | 'Windows' | 'macOS';

interface DeviceRecord {
  id: string;
  alias: string;
  os: OS;
  modelPack: string;
  packVersion: string;
  status: DeviceStatus;
  lastSeen: string;
  latencyP50: number;
  latencyP95: number;
  inferenceCount: number;
  errorRate: number;
  batteryDrain: 'low' | 'normal' | 'high';
}

interface MetricPoint { t: number; v: number }

// ─── Mock 데이터 ──────────────────────────────────────────────────────────────

const MOCK_DEVICES: DeviceRecord[] = [
  { id: 'd-001', alias: 'Galaxy S24 Ultra', os: 'Android', modelPack: 'ko-en-1.5b-v2', packVersion: '2.1.3', status: 'online',   lastSeen: '방금',    latencyP50: 298, latencyP95: 510, inferenceCount: 3421, errorRate: 0.002, batteryDrain: 'low' },
  { id: 'd-002', alias: 'iPhone 15 Pro',    os: 'iOS',     modelPack: 'ko-en-1.5b-v2', packVersion: '2.1.3', status: 'online',   lastSeen: '1분 전',  latencyP50: 271, latencyP95: 468, inferenceCount: 5102, errorRate: 0.001, batteryDrain: 'low' },
  { id: 'd-003', alias: 'Pixel 8',          os: 'Android', modelPack: 'ko-en-3b-v1',   packVersion: '1.2.0', status: 'online',   lastSeen: '2분 전',  latencyP50: 492, latencyP95: 820, inferenceCount: 812,  errorRate: 0.008, batteryDrain: 'normal' },
  { id: 'd-004', alias: 'Galaxy Tab S9',    os: 'Android', modelPack: 'ko-en-3b-v1',   packVersion: '1.2.0', status: 'degraded', lastSeen: '8분 전',  latencyP50: 891, latencyP95: 1430, inferenceCount: 234,  errorRate: 0.041, batteryDrain: 'high' },
  { id: 'd-005', alias: 'MacBook M3 Pro',   os: 'macOS',   modelPack: 'ko-en-1.5b-v2', packVersion: '2.1.3', status: 'online',   lastSeen: '방금',    latencyP50: 189, latencyP95: 302, inferenceCount: 8821, errorRate: 0.000, batteryDrain: 'low' },
  { id: 'd-006', alias: 'Surface Pro 9',    os: 'Windows', modelPack: 'ko-en-1.5b-v2', packVersion: '2.1.2', status: 'updating', lastSeen: '3분 전',  latencyP50: 0,   latencyP95: 0,   inferenceCount: 1205, errorRate: 0.000, batteryDrain: 'normal' },
  { id: 'd-007', alias: 'Xiaomi 13',        os: 'Android', modelPack: 'ko-en-1.5b-v2', packVersion: '2.1.3', status: 'offline',  lastSeen: '2시간 전', latencyP50: 0,   latencyP95: 0,   inferenceCount: 441,  errorRate: 0.000, batteryDrain: 'normal' },
];

// 간단한 스파크라인용 mock 데이터
const makeSparkline = (base: number, len = 12): MetricPoint[] =>
  Array.from({ length: len }, (_, i) => ({
    t: i,
    v: Math.max(0, base + (Math.random() - 0.5) * base * 0.4),
  }));

// ─── 유틸 ─────────────────────────────────────────────────────────────────────

const STATUS_META: Record<DeviceStatus, { label: string; dot: string; row: string }> = {
  online:   { label: 'Online',   dot: 'bg-emerald-500',              row: '' },
  offline:  { label: 'Offline',  dot: 'bg-gray-300',                 row: 'opacity-50' },
  degraded: { label: 'Degraded', dot: 'bg-amber-500 animate-pulse',  row: 'bg-amber-50/50' },
  updating: { label: 'Updating', dot: 'bg-blue-500 animate-pulse',   row: 'bg-blue-50/30' },
};

const OS_ICON: Record<OS, string> = {
  Android: '🤖', iOS: '', Windows: '🖥', macOS: '🍎',
};

const latencyColor = (ms: number) =>
  ms === 0 ? 'text-gray-300' : ms < 400 ? 'text-emerald-600' : ms < 800 ? 'text-amber-600' : 'text-red-600';

const errColor = (r: number) =>
  r < 0.01 ? 'text-emerald-600' : r < 0.03 ? 'text-amber-600' : 'text-red-600';

// ─── Sparkline ────────────────────────────────────────────────────────────────

const Sparkline: React.FC<{ data: MetricPoint[]; color?: string }> = ({ data, color = '#6366f1' }) => {
  if (!data.length) return null;
  const w = 80, h = 24;
  const xs = data.map(d => d.t);
  const ys = data.map(d => d.v);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const px = (x: number) => ((x - minX) / (maxX - minX || 1)) * w;
  const py = (y: number) => h - ((y - minY) / (maxY - minY || 1)) * h;
  const points = data.map(d => `${px(d.t)},${py(d.v)}`).join(' ');

  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
};

// ─── 메인 ─────────────────────────────────────────────────────────────────────

export const OnDeviceStatusPage: React.FC = () => {
  const [devices] = useState<DeviceRecord[]>(MOCK_DEVICES);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState<DeviceStatus | 'all'>('all');
  const [latencyData] = useState(() => makeSparkline(340));
  const [errorData] = useState(() => makeSparkline(0.005));
  const [lastUpdated, setLastUpdated] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setLastUpdated(new Date()), 30000);
    return () => clearInterval(t);
  }, []);

  const filtered = devices.filter(d => {
    const matchSearch = d.alias.toLowerCase().includes(search.toLowerCase()) ||
                        d.modelPack.toLowerCase().includes(search.toLowerCase());
    const matchStatus = filterStatus === 'all' || d.status === filterStatus;
    return matchSearch && matchStatus;
  });

  const counts = {
    online:   devices.filter(d => d.status === 'online').length,
    degraded: devices.filter(d => d.status === 'degraded').length,
    offline:  devices.filter(d => d.status === 'offline').length,
    updating: devices.filter(d => d.status === 'updating').length,
  };

  const avgLatency = Math.round(
    devices.filter(d => d.latencyP50 > 0).reduce((s, d) => s + d.latencyP50, 0) /
    devices.filter(d => d.latencyP50 > 0).length
  );

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">

      {/* 헤더 */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">온디바이스 AI 상태</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            기기별 모델 로드 · 추론 성능 · 이상 감지
            <span className="ml-3 text-xs">업데이트: {lastUpdated.toLocaleTimeString('ko-KR')}</span>
          </p>
        </div>
        <div className="flex gap-2">
          <span className="px-2.5 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs font-medium">
            ● {counts.online} Online
          </span>
          {counts.degraded > 0 && (
            <span className="px-2.5 py-1 bg-amber-100 text-amber-700 rounded-full text-xs font-medium">
              ● {counts.degraded} Degraded
            </span>
          )}
          {counts.updating > 0 && (
            <span className="px-2.5 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
              ↻ {counts.updating} Updating
            </span>
          )}
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-400">총 등록 기기</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{devices.length.toLocaleString()}</p>
          <Sparkline data={makeSparkline(devices.length, 8)} color="#6366f1" />
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-400">평균 P50 지연</p>
          <p className={`text-2xl font-bold mt-1 ${latencyColor(avgLatency)}`}>{avgLatency}ms</p>
          <Sparkline data={latencyData} color="#10b981" />
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-400">총 추론 횟수 (오늘)</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">
            {devices.reduce((s, d) => s + d.inferenceCount, 0).toLocaleString()}
          </p>
          <Sparkline data={makeSparkline(2000, 8)} color="#8b5cf6" />
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-400">평균 에러율</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">
            {(devices.reduce((s, d) => s + d.errorRate, 0) / devices.length * 100).toFixed(2)}%
          </p>
          <Sparkline data={errorData} color="#f59e0b" />
        </div>
      </div>

      {/* 필터 */}
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="기기명 또는 팩 이름 검색..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 w-64"
        />
        <div className="flex gap-1">
          {(['all', 'online', 'degraded', 'updating', 'offline'] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors ${
                filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {s === 'all' ? '전체' : STATUS_META[s].label}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-400 ml-auto">{filtered.length}개 기기</span>
      </div>

      {/* 테이블 */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/70">
              {['기기', 'OS', '모델팩', '상태', 'P50', 'P95', '추론', '에러율', '배터리', '최근 접속'].map(h => (
                <th key={h} className="py-2.5 px-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wide first:pl-4 last:pr-4">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(d => {
              const sm = STATUS_META[d.status];
              return (
                <tr key={d.id} className={`border-b border-gray-50 hover:bg-gray-50/60 transition-colors ${sm.row}`}>
                  <td className="py-3 pl-4 pr-2">
                    <p className="font-medium text-gray-900">{d.alias}</p>
                    <p className="text-xs text-gray-400 font-mono">{d.id}</p>
                  </td>
                  <td className="py-3 px-2 text-base">{OS_ICON[d.os]}</td>
                  <td className="py-3 px-2">
                    <p className="font-mono text-xs text-gray-700">{d.modelPack}</p>
                    <p className="text-xs text-gray-400">v{d.packVersion}</p>
                  </td>
                  <td className="py-3 px-2">
                    <span className="inline-flex items-center gap-1.5 text-xs">
                      <span className={`w-1.5 h-1.5 rounded-full ${sm.dot}`} />
                      {sm.label}
                    </span>
                  </td>
                  <td className={`py-3 px-2 font-mono text-xs ${latencyColor(d.latencyP50)}`}>
                    {d.latencyP50 > 0 ? `${d.latencyP50}ms` : '—'}
                  </td>
                  <td className={`py-3 px-2 font-mono text-xs ${latencyColor(d.latencyP95)}`}>
                    {d.latencyP95 > 0 ? `${d.latencyP95}ms` : '—'}
                  </td>
                  <td className="py-3 px-2 text-xs text-gray-600 tabular-nums">
                    {d.inferenceCount.toLocaleString()}
                  </td>
                  <td className={`py-3 px-2 font-mono text-xs ${errColor(d.errorRate)}`}>
                    {(d.errorRate * 100).toFixed(2)}%
                  </td>
                  <td className="py-3 px-2 text-xs">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      d.batteryDrain === 'low'    ? 'bg-emerald-100 text-emerald-700' :
                      d.batteryDrain === 'normal' ? 'bg-gray-100 text-gray-600' :
                                                    'bg-red-100 text-red-600'
                    }`}>
                      {d.batteryDrain === 'low' ? '🔋 낮음' : d.batteryDrain === 'normal' ? '🔋 보통' : '🔋 높음'}
                    </span>
                  </td>
                  <td className="py-3 pl-2 pr-4 text-xs text-gray-400">{d.lastSeen}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400 mt-3">
        * 현재 mock 데이터입니다. Phase B 완료 후 실제 기기 데이터가 연결됩니다.
      </p>
    </div>
  );
};

export default OnDeviceStatusPage;
