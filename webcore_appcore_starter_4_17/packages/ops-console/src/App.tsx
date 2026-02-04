/**
 * Ops Console 메인 앱
 * 
 * @module App
 */

import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
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

function AppContent() {
  const { permission, setPermission } = useAuth();
  
  // OS 역할 (환경변수에서 읽기, 나중에 SSO로 교체)
  const osRole = (import.meta.env.VITE_OS_ROLE || 'operator') as 'operator' | 'auditor' | 'admin';
  const isOperator = osRole === 'operator';
  const isAuditor = osRole === 'auditor' || osRole === 'admin';

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 네비게이션 */}
      <nav className="bg-white shadow">
        <div className="container mx-auto px-4">
          <div className="flex justify-between items-center h-16">
            <div className="flex space-x-8">
              <Link
                to="/os/dashboard"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium font-bold"
              >
                OS Dashboard
              </Link>
              <Link
                to="/reports"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                Reports
              </Link>
              <Link
                to="/timeline"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                Timeline
              </Link>
              <Link
                to="/demo/accounting"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                회계 데모
              </Link>
              {/* Export 메뉴: operator는 조회만, auditor는 전체 */}
              <Link
                to="/exports"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isOperator 
                    ? 'text-gray-400 cursor-not-allowed' 
                    : 'text-gray-700 hover:text-gray-900'
                }`}
                onClick={(e) => {
                  if (isOperator) {
                    e.preventDefault();
                  }
                }}
                title={isOperator ? 'Export는 auditor 이상 권한이 필요합니다' : ''}
              >
                Export {isOperator && '(조회만)'}
              </Link>
              {/* Audit 메뉴: operator는 읽기 전용, auditor는 전체 */}
              <Link
                to="/audit"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isOperator 
                    ? 'text-gray-500' 
                    : 'text-gray-700 hover:text-gray-900'
                }`}
                title={isOperator ? 'Audit은 읽기 전용입니다' : 'Audit 전체 조회 가능'}
              >
                Audit {isOperator && '(읽기 전용)'}
              </Link>
              {/* Manual Review 메뉴 */}
              <Link
                to="/manual-review"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                Manual Review
              </Link>
              {/* CS 메뉴 */}
              <Link
                to="/cs"
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
              >
                CS
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-600">
                Role: <strong>{osRole}</strong>
              </span>
              <span className="text-sm text-gray-600">
                Permission: <strong>{permission}</strong>
              </span>
              <select
                value={permission}
                onChange={(e) => setPermission(e.target.value as 'read-only' | 'download')}
                className="px-3 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="read-only">Read Only</option>
                <option value="download">Download</option>
              </select>
            </div>
          </div>
        </div>
      </nav>

      {/* 메인 컨텐츠 */}
      <main>
        <Routes>
          <Route path="/reports" element={<Reports />} />
          <Route
            path="/reports/:id"
            element={
              <ProtectedRoute requiredPermission="download">
                <ReportDetail />
              </ProtectedRoute>
            }
          />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="/os/dashboard" element={<OsDashboard />} />
          <Route path="/demo/accounting" element={<AccountingDemo />} />
          <Route path="/manual-review" element={<ManualReviewPage />} />
          <Route path="/cs" element={<CsDashboardPage />} />
          <Route path="/" element={<OsDashboard />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

