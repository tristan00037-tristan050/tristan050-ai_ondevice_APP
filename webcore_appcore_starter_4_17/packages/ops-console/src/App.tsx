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

function AppContent() {
  const { permission, setPermission } = useAuth();

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 네비게이션 */}
      <nav className="bg-white shadow">
        <div className="container mx-auto px-4">
          <div className="flex justify-between items-center h-16">
            <div className="flex space-x-8">
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
            </div>
            <div className="flex items-center space-x-4">
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
          <Route path="/" element={<Reports />} />
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

