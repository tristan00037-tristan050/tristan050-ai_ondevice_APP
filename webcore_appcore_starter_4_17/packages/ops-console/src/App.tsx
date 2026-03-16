/**
 * App.tsx (업데이트)
 * 기존 ops-console App.tsx에 ModelPackPage, OnDeviceStatusPage 추가
 *
 * 교체 위치: webcore_appcore_starter_4_17/packages/ops-console/src/App.tsx
 */

import { BrowserRouter, Routes, Route, Link, NavLink } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { useAuth } from './hooks/useAuth';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Reports } from './pages/Reports';
import { ReportDetail } from './pages/ReportDetail';
import { TimelinePage } from './pages/Timeline';
import AccountingDemo from './pages/demo/AccountingDemo';
import ManualReviewPage from './pages/manual-review/ManualReviewPage';
import OsDashboard from './pages/os/OsDashboard';
import { CsDashboardPage } from './pages/cs/CsDashboardPage';
// ↓ 신규 추가
import { ModelPackPage } from './pages/ai/ModelPackPage';
import { OnDeviceStatusPage } from './pages/ai/OnDeviceStatusPage';
import { RolloutPage } from './pages/rollout/RolloutPage';

const NAV_LINK_BASE = 'text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium transition-colors';
const NAV_LINK_ACTIVE = 'text-indigo-600 bg-indigo-50 font-semibold';

function AppContent() {
  const { permission, setPermission } = useAuth();
  const osRole = (import.meta.env.VITE_OS_ROLE || 'operator') as 'operator' | 'auditor' | 'admin';
  const isOperator = osRole === 'operator';

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="container mx-auto px-4">
          <div className="flex justify-between items-center h-14">

            {/* 로고 */}
            <div className="flex items-center gap-6">
              <Link to="/" className="font-bold text-indigo-600 text-sm tracking-tight">
                AI OnDevice ⬡
              </Link>

              <div className="flex items-center gap-0.5">
                {/* AI 섹션 (신규) */}
                <NavLink to="/ai/model-packs"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  모델팩
                </NavLink>
                <NavLink to="/ai/ondevice-status"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  기기 상태
                </NavLink>

                <NavLink to="/rollout"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  Rollout
                </NavLink>

                {/* 구분선 */}
                <span className="mx-1 text-gray-200">|</span>

                {/* 기존 메뉴 */}
                <NavLink to="/os/dashboard"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  OS 대시보드
                </NavLink>
                <NavLink to="/reports"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  Reports
                </NavLink>
                <NavLink to="/timeline"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  Timeline
                </NavLink>
                <NavLink to="/manual-review"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  Manual Review
                </NavLink>
                <NavLink to="/cs"
                  className={({ isActive }) => `${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : ''}`}>
                  CS
                </NavLink>
                <Link
                  to="/exports"
                  className={`${NAV_LINK_BASE} ${isOperator ? 'text-gray-300 cursor-not-allowed' : ''}`}
                  onClick={e => { if (isOperator) e.preventDefault(); }}
                >
                  Export {isOperator && <span className="text-xs">(조회만)</span>}
                </Link>
              </div>
            </div>

            {/* 권한 셀렉터 */}
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
                {osRole}
              </span>
              <select
                value={permission}
                onChange={e => setPermission(e.target.value as 'read-only' | 'download')}
                className="px-2 py-1 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                <option value="read-only">Read Only</option>
                <option value="download">Download</option>
              </select>
            </div>
          </div>
        </div>
      </nav>

      <main>
        <Routes>
          {/* ─── AI 신규 라우트 ─── */}
          <Route path="/ai/model-packs"      element={<ModelPackPage />} />
          <Route path="/ai/ondevice-status"  element={<OnDeviceStatusPage />} />

          {/* ─── Rollout ─── */}
          <Route path="/rollout" element={<RolloutPage />} />

          {/* ─── 기존 라우트 ─── */}
          <Route path="/reports"   element={<Reports />} />
          <Route path="/reports/:id" element={
            <ProtectedRoute requiredPermission="download"><ReportDetail /></ProtectedRoute>
          } />
          <Route path="/timeline"       element={<TimelinePage />} />
          <Route path="/os/dashboard"   element={<OsDashboard />} />
          <Route path="/demo/accounting" element={<AccountingDemo />} />
          <Route path="/manual-review"  element={<ManualReviewPage />} />
          <Route path="/cs"             element={<CsDashboardPage />} />

          {/* 기본: 모델팩 페이지 */}
          <Route path="/" element={<ModelPackPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}
