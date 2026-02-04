/**
 * useAuth Hook
 * Fast refresh를 위해 별도 파일로 분리
 * 
 * @module useAuth
 */

import { useContext } from 'react';
import { AuthContext } from '../contexts/AuthContext';

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};


