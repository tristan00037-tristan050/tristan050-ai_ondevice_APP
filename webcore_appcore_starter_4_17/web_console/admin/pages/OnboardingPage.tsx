/**
 * Onboarding Page
 * Complete enterprise onboarding via UI
 */

import React, { useState } from 'react';
import { tenantsApi, usersApi, rolesApi, CreateTenantRequest, CreateUserRequest, CreateRoleRequest } from '../api_client/api';
import { RBACGuard, useRBAC } from '../components/RBACGuard';
import { ErrorBoundary } from '../components/ErrorBoundary';

const STEPS = [
  { label: 'Create Tenant', num: 1 },
  { label: 'Create User', num: 2 },
  { label: 'Create Role', num: 3 },
];

export const OnboardingPage: React.FC = () => {
  const [step, setStep] = useState(1);
  const [tenantName, setTenantName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userName, setUserName] = useState('');
  const [roleName, setRoleName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [tenantId, setTenantId] = useState<string | null>(null);

  const handleCreateTenant = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await tenantsApi.create({ name: tenantName });
      setTenantId(response.tenant.id);
      setStep(2);
    } catch (err: any) {
      setError(err.message || 'Failed to create tenant');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async () => {
    if (!tenantId) {
      setError('Tenant ID is required');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await usersApi.create({
        tenant_id: tenantId,
        email: userEmail,
        name: userName,
      });
      setStep(3);
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRole = async () => {
    if (!tenantId) {
      setError('Tenant ID is required');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await rolesApi.create({
        tenant_id: tenantId,
        name: roleName,
        description: 'Default admin role',
        permissions: [
          'tenant:read',
          'tenant:write',
          'user:read',
          'user:write',
          'role:read',
          'role:write',
          'audit:read',
        ],
      });
      setCompleted(true);
    } catch (err: any) {
      setError(err.message || 'Failed to create role');
    } finally {
      setLoading(false);
    }
  };

  if (completed) {
    return (
      <div className="max-w-lg mx-auto px-6 py-16 text-center">
        <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-6">
          <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Onboarding Complete!</h1>
        <p className="text-sm text-gray-500 mb-4">Your enterprise account has been set up successfully.</p>
        <div className="inline-block px-4 py-2 bg-gray-100 rounded-lg text-xs font-mono text-gray-600">
          Tenant ID: {tenantId}
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-lg mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Setup</p>
          <h1 className="text-xl font-bold text-gray-900">Enterprise Onboarding</h1>
        </div>

        {/* Step indicators */}
        <div className="flex items-center mb-8">
          {STEPS.map((s, idx) => (
            <React.Fragment key={s.num}>
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                    step > s.num
                      ? 'bg-emerald-500 text-white'
                      : step === s.num
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {step > s.num ? (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    s.num
                  )}
                </div>
                <span className={`text-xs font-medium hidden sm:block ${
                  step === s.num ? 'text-indigo-600' : step > s.num ? 'text-emerald-600' : 'text-gray-400'
                }`}>
                  {s.label}
                </span>
              </div>
              {idx < STEPS.length - 1 && (
                <div className={`flex-1 h-px mx-3 ${step > s.num ? 'bg-emerald-300' : 'bg-gray-200'}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
            {error}
          </div>
        )}

        {/* Step content */}
        <div className="border border-gray-200 rounded-xl bg-white shadow-sm p-6">
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900 mb-1">Step 1: Create Tenant</h2>
                <p className="text-xs text-gray-500">Set up your organization's tenant workspace.</p>
              </div>
              <input
                type="text"
                placeholder="Tenant name"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <button
                onClick={handleCreateTenant}
                disabled={loading || !tenantName.trim()}
                className="w-full py-2.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors"
              >
                {loading ? 'Creating...' : 'Create Tenant →'}
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900 mb-1">Step 2: Create User</h2>
                <p className="text-xs text-gray-500">Add the first admin user for this tenant.</p>
              </div>
              <input
                type="email"
                placeholder="Email"
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <input
                type="text"
                placeholder="Name"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <button
                onClick={handleCreateUser}
                disabled={loading || !userEmail.trim() || !userName.trim()}
                className="w-full py-2.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors"
              >
                {loading ? 'Creating...' : 'Create User →'}
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900 mb-1">Step 3: Create Role</h2>
                <p className="text-xs text-gray-500">Define the default admin role with standard permissions.</p>
              </div>
              <input
                type="text"
                placeholder="Role name"
                value={roleName}
                onChange={(e) => setRoleName(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <div className="px-3 py-2 bg-gray-50 border border-gray-100 rounded-lg">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Default permissions</p>
                <div className="flex flex-wrap gap-1">
                  {['tenant:read', 'tenant:write', 'user:read', 'user:write', 'role:read', 'role:write', 'audit:read'].map((p) => (
                    <span key={p} className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">{p}</span>
                  ))}
                </div>
              </div>
              <button
                onClick={handleCreateRole}
                disabled={loading || !roleName.trim()}
                className="w-full py-2.5 text-sm font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-40 transition-colors"
              >
                {loading ? 'Creating...' : 'Complete Onboarding'}
              </button>
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
};
