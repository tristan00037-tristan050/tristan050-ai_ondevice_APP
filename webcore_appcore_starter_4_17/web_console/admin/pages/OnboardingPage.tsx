/**
 * Onboarding Page
 * Complete enterprise onboarding via UI
 */

import React, { useState } from 'react';
import { tenantsApi, usersApi, rolesApi, CreateTenantRequest, CreateUserRequest, CreateRoleRequest } from '../api_client/api';
import { RBACGuard, useRBAC } from '../components/RBACGuard';
import { ErrorBoundary } from '../components/ErrorBoundary';

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
      <div className="onboarding-complete">
        <h1>Onboarding Complete!</h1>
        <p>Your enterprise account has been set up successfully.</p>
        <p>Tenant ID: {tenantId}</p>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="onboarding-page">
        <h1>Enterprise Onboarding</h1>
        <div className="onboarding-steps">
          <div className={`step ${step >= 1 ? 'active' : ''}`}>1. Create Tenant</div>
          <div className={`step ${step >= 2 ? 'active' : ''}`}>2. Create User</div>
          <div className={`step ${step >= 3 ? 'active' : ''}`}>3. Create Role</div>
        </div>

        {error && <div className="error">{error}</div>}

        {step === 1 && (
          <div className="onboarding-step">
            <h2>Step 1: Create Tenant</h2>
            <input
              type="text"
              placeholder="Tenant name"
              value={tenantName}
              onChange={(e) => setTenantName(e.target.value)}
              disabled={loading}
            />
            <button onClick={handleCreateTenant} disabled={loading || !tenantName.trim()}>
              {loading ? 'Creating...' : 'Create Tenant'}
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="onboarding-step">
            <h2>Step 2: Create User</h2>
            <input
              type="email"
              placeholder="Email"
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
              disabled={loading}
            />
            <input
              type="text"
              placeholder="Name"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              disabled={loading}
            />
            <button onClick={handleCreateUser} disabled={loading || !userEmail.trim() || !userName.trim()}>
              {loading ? 'Creating...' : 'Create User'}
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="onboarding-step">
            <h2>Step 3: Create Role</h2>
            <input
              type="text"
              placeholder="Role name"
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
              disabled={loading}
            />
            <button onClick={handleCreateRole} disabled={loading || !roleName.trim()}>
              {loading ? 'Creating...' : 'Complete Onboarding'}
            </button>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
};

