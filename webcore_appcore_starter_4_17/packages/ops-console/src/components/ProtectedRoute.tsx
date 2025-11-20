/**
 * 보호된 라우트 컴포넌트
 * 권한에 따른 접근 제어
 * 
 * @module ProtectedRoute
 */

import React, { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Permission } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
  requiredPermission?: Permission;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredPermission,
}) => {
  const { permission } = useAuth();

  // 권한이 필요한 경우 체크
  if (requiredPermission) {
    if (requiredPermission === 'download' && permission === 'read-only') {
      // 다운로드 권한이 필요한데 읽기 전용인 경우
      return (
        <div className="container mx-auto px-4 py-8">
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded">
            <p className="font-semibold">Access Denied</p>
            <p className="text-sm mt-1">
              This page requires download permission. Your current permission is: <strong>read-only</strong>
            </p>
          </div>
        </div>
      );
    }
  }

  return <>{children}</>;
};

