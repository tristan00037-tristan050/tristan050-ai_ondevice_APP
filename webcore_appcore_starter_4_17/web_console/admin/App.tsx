/**
 * Admin Console App
 * Main application component
 */

import React, { useState } from 'react';
import { RBACProvider } from './components/RBACGuard';
import { ErrorBoundary } from './components/ErrorBoundary';
import { OnboardingPage } from './pages/OnboardingPage';
import { TenantsPage } from './pages/TenantsPage';
import { UsersPage } from './pages/UsersPage';
import { RolesPage } from './pages/RolesPage';

// Mock permissions (in production, get from auth context)
const getUserPermissions = (): string[] => {
  // In production, extract from JWT token or auth context
  const token = sessionStorage.getItem('auth_token');
  if (!token) {
    return [];
  }
  // Mock: return all permissions for admin user
  // In production, decode JWT and extract permissions
  return [
    'tenant:read',
    'tenant:write',
    'user:read',
    'user:write',
    'role:read',
    'role:write',
    'audit:read',
  ];
};

export const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<'onboarding' | 'tenants' | 'users' | 'roles'>('onboarding');
  const permissions = getUserPermissions();

  return (
    <ErrorBoundary>
      <RBACProvider permissions={permissions}>
        <div className="admin-console">
          <nav className="admin-nav">
            <button onClick={() => setCurrentPage('onboarding')}>Onboarding</button>
            <button onClick={() => setCurrentPage('tenants')}>Tenants</button>
            <button onClick={() => setCurrentPage('users')}>Users</button>
            <button onClick={() => setCurrentPage('roles')}>Roles</button>
          </nav>

          <main className="admin-main">
            {currentPage === 'onboarding' && <OnboardingPage />}
            {currentPage === 'tenants' && <TenantsPage />}
            {currentPage === 'users' && <UsersPage />}
            {currentPage === 'roles' && <RolesPage />}
          </main>
        </div>
      </RBACProvider>
    </ErrorBoundary>
  );
};

