/**
 * 인증 및 권한 컨텍스트
 * 읽기 전용/다운로드 가능 권한 분리
 * 
 * @module AuthContext
 */

/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useState, useEffect, ReactNode } from 'react';

export type Permission = 'read-only' | 'download';

export interface AuthContextType {
  permission: Permission;
  setPermission: (permission: Permission) => void;
  canDownload: boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  // 환경 변수에서 권한 읽기 (기본값: download)
  const defaultPermission = (import.meta.env.VITE_PERMISSION as Permission) || 'download';
  const [permission, setPermission] = useState<Permission>(defaultPermission);

  // localStorage에서 권한 읽기 (세션 유지)
  useEffect(() => {
    const stored = localStorage.getItem('ops-console-permission') as Permission | null;
    if (stored && (stored === 'read-only' || stored === 'download')) {
      setPermission(stored);
    }
  }, []);

  // 권한 변경 시 localStorage에 저장
  useEffect(() => {
    localStorage.setItem('ops-console-permission', permission);
  }, [permission]);

  const canDownload = permission === 'download';

  return (
    <AuthContext.Provider value={{ permission, setPermission, canDownload }}>
      {children}
    </AuthContext.Provider>
  );
};

