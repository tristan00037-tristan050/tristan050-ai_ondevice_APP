/**
 * ModelPackPage.tsx
 * AI 모델팩 관리 페이지 — 모델팩 목록, 버전, 배포 상태, 롤아웃 제어
 */

import React, { useState, useEffect } from 'react';

// ─── 타입 ────────────────────────────────────────────────────────────────────

type PackStatus = 'active' | 'staged' | 'rollback' | 'deprecated' | 'training';
type DeployPhase = 'A' | 'B' | 'C' | 'D';

interface ModelPack {
  id: string;
  name: string;
  version: string;
  baseModel: string;
  status: PackStatus;
  canaryPercent: number;
  killSwitch: boolean;
  deployPhase: DeployPhase;
  trainedAt: string | null;
  deployedAt: string | null;
  deviceCount: number;
  avgLatencyMs: number | null;
  accuracy: number | null;
  sizeGb: number;
}

interface TrainingRun {
  phase: DeployPhase;
  label: string;
  status: 'done' | 'running' | 'pending' | 'blocked';
  completedAt: string | null;
  condition: string;
}

// ─── Mock 데이터 ──────────────────────────────────────────────────────────────

const MOCK_PACKS: ModelPack[] = [
  {
    id: 'pack-001',
    name: 'ko-en-7b-v1',
    version: '1.0.0',
    baseModel: 'Qwen2.5-7B-Instruct',
    status: 'training',
    canaryPercent: 0,
    killSwitch: false,
    deployPhase: 'A',
    trainedAt: null,
    deployedAt: null,
    deviceCount: 0,
    avgLatencyMs: null,
    accuracy: null,
    sizeGb: 4.2,
  },
  {
    id: 'pack-002',
    name: 'ko-en-1.5b-v2',
    version: '2.1.3',
    baseModel: 'Qwen2.5-1.5B-Instruct',
    status: 'active',
    canaryPercent: 100,
    killSwitch: false,
    deployPhase: 'D',
    trainedAt: '2026-02-14T09:22:00Z',
    deployedAt: '2026-02-20T14:00:00Z',
    deviceCount: 1284,
    avgLatencyMs: 312,
    accuracy: 0.847,
    sizeGb: 1.1,
  },
  {
    id: 'pack-003',
    name: 'ko-en-3b-v1',
    version: '1.2.0',
    baseModel: 'Qwen2.5-3B-Instruct',
    status: 'staged',
    canaryPercent: 15,
    killSwitch: false,
    deployPhase: 'C',
    trainedAt: '2026-03-01T11:00:00Z',
    deployedAt: null,
    deviceCount: 193,
    avgLatencyMs: 487,
    accuracy: 0.871,
    sizeGb: 2.0,
  },
  {
    id: 'pack-004',
    name: 'ko-en-1.5b-v1',
    version: '1.0.8',
    baseModel: 'Qwen2.5-1.5B-Instruct',
    status: 'deprecated',
    canaryPercent: 0,
    killSwitch: true,
    deployPhase: 'D',
    trainedAt: '2025-12-10T08:00:00Z',
    deployedAt: '2025-12-20T12:00:00Z',
    deviceCount: 0,
    avgLatencyMs: 298,
    accuracy: 0.812,
    sizeGb: 1.1,
  },
];

const TRAINING_PHASES: TrainingRun[] = [
  { phase: 'A', label: 'Phase A — 알고리즘 기반', status: 'done', completedAt: '2026-03-16', condition: 'DoD 15/15 ✅' },
  { phase: 'B', label: 'Phase B — GPU 실제 학습', status: 'blocked', completedAt: null, condition: 'PC-A (RTX 5080+) 확보 필요' },
  { phase: 'C', label: 'Phase C — Checkpoint + Eval', status: 'pending', completedAt: null, condition: 'Phase B 완료 후' },
  { phase: 'D', label: 'Phase D — Verified 전환', status: 'pending', completedAt: null, condition: 'Phase C 완료 후' },
];

// ─── 유틸 ─────────────────────────────────────────────────────────────────────

const STATUS_META: Record<PackStatus, { label: string; color: string; dot: string }> = {
  active:     { label: 'Active',      color: 'bg-emerald-100 text-emerald-800 border-emerald-200',   dot: 'bg-emerald-500' },
  staged:     { label: 'Staged',      color: 'bg-blue-100 text-blue-800 border-blue-200',            dot: 'bg-blue-500' },
  rollback:   { label: 'Rollback',    color: 'bg-amber-100 text-amber-800 border-amber-200',         dot: 'bg-amber-500' },
  deprecated: { label: 'Deprecated',  color: 'bg-gray-100 text-gray-500 border-gray-200',            dot: 'bg-gray-400' },
  training:   { label: 'Training',    color: 'bg-violet-100 text-violet-800 border-violet-200',      dot: 'bg-violet-500 animate-pulse' },
};

const PHASE_META: Record<TrainingRun['status'], { color: string; icon: string }> = {
  done:    { color: 'text-emerald-600', icon: '✓' },
  running: { color: 'text-blue-600',    icon: '⟳' },
  blocked: { color: 'text-amber-600',   icon: '⚠' },
  pending: { color: 'text-gray-400',    icon: '○' },
};

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', year: '2-digit' }) : '—';

// ─── 서브 컴포넌트 ────────────────────────────────────────────────────────────

const StatusBadge: React.FC<{ status: PackStatus }> = ({ status }) => {
  const m = STATUS_META[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${m.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
};

const CanaryBar: React.FC<{ percent: number; disabled?: boolean }> = ({ percent, disabled }) => (
  <div className="flex items-center gap-2">
    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${disabled ? 'bg-gray-300' : 'bg-indigo-500'}`}
        style={{ width: `${percent}%` }}
      />
    </div>
    <span className="text-xs tabular-nums text-gray-500 w-8 text-right">{percent}%</span>
  </div>
);

const PackRow: React.FC<{
  pack: ModelPack;
  onToggleKill: (id: string) => void;
  onCanaryChange: (id: string, v: number) => void;
}> = ({ pack, onToggleKill, onCanaryChange }) => {
  const [expanded, setExpanded] = useState(false);
  const isEditable = pack.status !== 'deprecated' && pack.status !== 'training';

  return (
    <>
      <tr
        className="border-b border-gray-50 hover:bg-gray-50/60 cursor-pointer transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <td className="py-3 pl-4 pr-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-300">{expanded ? '▾' : '▸'}</span>
            <div>
              <div className="font-mono text-sm font-medium text-gray-900">{pack.name}</div>
              <div className="text-xs text-gray-400">{pack.baseModel}</div>
            </div>
          </div>
        </td>
        <td className="py-3 px-2">
          <span className="font-mono text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">v{pack.version}</span>
        </td>
        <td className="py-3 px-2"><StatusBadge status={pack.status} /></td>
        <td className="py-3 px-2 w-36"><CanaryBar percent={pack.canaryPercent} disabled={!isEditable} /></td>
        <td className="py-3 px-2 text-sm text-gray-500 tabular-nums">
          {pack.deviceCount > 0 ? pack.deviceCount.toLocaleString() : '—'}
        </td>
        <td className="py-3 px-2 text-sm text-gray-500 tabular-nums">
          {pack.avgLatencyMs != null ? `${pack.avgLatencyMs}ms` : '—'}
        </td>
        <td className="py-3 px-2 text-sm text-gray-500">
          {pack.accuracy != null ? `${(pack.accuracy * 100).toFixed(1)}%` : '—'}
        </td>
        <td className="py-3 pl-2 pr-4 text-sm text-gray-400">{fmt(pack.deployedAt)}</td>
      </tr>

      {expanded && (
        <tr className="bg-indigo-50/30 border-b border-indigo-100">
          <td colSpan={8} className="py-4 px-8">
            <div className="grid grid-cols-3 gap-6">
              {/* 카나리 조절 */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">카나리 배포</p>
                {isEditable ? (
                  <div className="flex items-center gap-3">
                    <input
                      type="range" min={0} max={100} step={5}
                      value={pack.canaryPercent}
                      onChange={e => onCanaryChange(pack.id, Number(e.target.value))}
                      className="flex-1 accent-indigo-600"
                      onClick={e => e.stopPropagation()}
                    />
                    <span className="text-sm font-mono w-10 text-right">{pack.canaryPercent}%</span>
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">편집 불가 ({pack.status})</p>
                )}
              </div>

              {/* 킬스위치 */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">킬 스위치</p>
                <button
                  onClick={e => { e.stopPropagation(); if (isEditable) onToggleKill(pack.id); }}
                  disabled={!isEditable}
                  className={`px-3 py-1.5 rounded text-xs font-semibold transition-colors ${
                    pack.killSwitch
                      ? 'bg-red-100 text-red-700 border border-red-200 hover:bg-red-200'
                      : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {pack.killSwitch ? '🔴 ON — 즉시 차단 중' : '⚪ OFF — 정상 서빙'}
                </button>
              </div>

              {/* 메타 */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">상세 정보</p>
                <dl className="text-xs space-y-1 text-gray-600">
                  <div className="flex gap-2"><dt className="text-gray-400 w-20">Phase</dt><dd>{pack.deployPhase}</dd></div>
                  <div className="flex gap-2"><dt className="text-gray-400 w-20">크기</dt><dd>{pack.sizeGb} GB</dd></div>
                  <div className="flex gap-2"><dt className="text-gray-400 w-20">학습 완료</dt><dd>{fmt(pack.trainedAt)}</dd></div>
                  <div className="flex gap-2"><dt className="text-gray-400 w-20">Pack ID</dt><dd className="font-mono">{pack.id}</dd></div>
                </dl>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

const TrainingPipeline: React.FC = () => (
  <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
    <h2 className="text-sm font-semibold text-gray-700 mb-4">학습 파이프라인 (AI-16)</h2>
    <div className="flex items-start gap-0">
      {TRAINING_PHASES.map((p, i) => {
        const m = PHASE_META[p.status];
        return (
          <div key={p.phase} className="flex-1 relative">
            {/* 연결선 */}
            {i < TRAINING_PHASES.length - 1 && (
              <div className={`absolute top-4 left-1/2 w-full h-0.5 ${
                p.status === 'done' ? 'bg-emerald-300' : 'bg-gray-200'
              }`} />
            )}
            <div className="relative flex flex-col items-center text-center px-2">
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-sm font-bold z-10 bg-white ${
                p.status === 'done'    ? 'border-emerald-400 text-emerald-600' :
                p.status === 'running' ? 'border-blue-400 text-blue-600' :
                p.status === 'blocked' ? 'border-amber-400 text-amber-600' :
                                         'border-gray-200 text-gray-300'
              }`}>
                <span className={p.status === 'running' ? 'animate-spin inline-block' : ''}>
                  {m.icon}
                </span>
              </div>
              <p className={`mt-2 text-xs font-medium ${m.color}`}>{p.label}</p>
              <p className="text-xs text-gray-400 mt-0.5">{p.condition}</p>
              {p.completedAt && (
                <p className="text-xs text-emerald-600 mt-0.5">{p.completedAt}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

// ─── 메인 페이지 ──────────────────────────────────────────────────────────────

export const ModelPackPage: React.FC = () => {
  const [packs, setPacks] = useState<ModelPack[]>(MOCK_PACKS);
  const [filter, setFilter] = useState<PackStatus | 'all'>('all');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleToggleKill = (id: string) => {
    setPacks(prev => prev.map(p => p.id === id ? { ...p, killSwitch: !p.killSwitch } : p));
    const pack = packs.find(p => p.id === id)!;
    showToast(`${pack.name} 킬스위치 ${pack.killSwitch ? 'OFF' : 'ON'} 설정됨`);
  };

  const handleCanaryChange = (id: string, v: number) => {
    setPacks(prev => prev.map(p => p.id === id ? { ...p, canaryPercent: v } : p));
  };

  const handleApply = async () => {
    setSaving(true);
    await new Promise(r => setTimeout(r, 800));
    setSaving(false);
    showToast('모든 변경사항이 적용됐습니다.');
  };

  const filtered = filter === 'all' ? packs : packs.filter(p => p.status === filter);

  const stats = {
    active: packs.filter(p => p.status === 'active').length,
    staged: packs.filter(p => p.status === 'staged').length,
    training: packs.filter(p => p.status === 'training').length,
    totalDevices: packs.reduce((s, p) => s + p.deviceCount, 0),
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">

      {/* 토스트 */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-gray-900 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg animate-fade-in">
          {toast}
        </div>
      )}

      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">모델팩 관리</h1>
          <p className="text-sm text-gray-500 mt-0.5">온디바이스 AI 모델팩 배포 및 롤아웃 제어</p>
        </div>
        <button
          onClick={handleApply}
          disabled={saving}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors flex items-center gap-2"
        >
          {saving ? (
            <><span className="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />저장 중...</>
          ) : '변경사항 적용'}
        </button>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: '활성 팩',     value: stats.active,                    color: 'text-emerald-600' },
          { label: '스테이징 중', value: stats.staged,                    color: 'text-blue-600' },
          { label: '학습 중',     value: stats.training,                  color: 'text-violet-600' },
          { label: '총 기기 수',  value: stats.totalDevices.toLocaleString(), color: 'text-gray-900' },
        ].map(s => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-400 font-medium">{s.label}</p>
            <p className={`text-2xl font-bold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* 학습 파이프라인 */}
      <TrainingPipeline />

      {/* 필터 탭 */}
      <div className="flex items-center gap-1 mb-4">
        {(['all', 'active', 'staged', 'training', 'deprecated'] as const).map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              filter === s
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {s === 'all' ? '전체' : STATUS_META[s].label}
            <span className="ml-1.5 tabular-nums">
              {s === 'all' ? packs.length : packs.filter(p => p.status === s).length}
            </span>
          </button>
        ))}
      </div>

      {/* 테이블 */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/70">
              {['팩 이름', '버전', '상태', '카나리', '기기 수', '지연시간', '정확도', '배포일'].map(h => (
                <th key={h} className="py-2.5 px-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wide first:pl-4 last:pr-4">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(pack => (
              <PackRow
                key={pack.id}
                pack={pack}
                onToggleKill={handleToggleKill}
                onCanaryChange={handleCanaryChange}
              />
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="py-12 text-center text-gray-400 text-sm">
                  해당 상태의 모델팩이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400 mt-3">
        * Phase B (GPU 학습) 완료 후 ko-en-7b-v1 팩이 활성화됩니다.
      </p>
    </div>
  );
};

export default ModelPackPage;
