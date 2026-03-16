/**
 * Tenants Page
 * Manage tenants (RBAC enforced)
 */

import React, { useState, useEffect } from 'react';
import { tenantsApi, Tenant, CreateTenantRequest } from '../api_client/api';
import { RBACGuard, RBACButton, useRBAC } from '../components/RBACGuard';
import { ErrorBoundary } from '../components/ErrorBoundary';

export const TenantsPage: React.FC = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { hasPermission } = useRBAC();

  useEffect(() => {
    loadTenants();
  }, []);

  const loadTenants = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await tenantsApi.list();
      setTenants(response.tenants);
    } catch (err: any) {
      setError(err.message || 'Failed to load tenants');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (request: CreateTenantRequest) => {
    try {
      setError(null);
      await tenantsApi.create(request);
      setShowCreateForm(false);
      await loadTenants();
    } catch (err: any) {
      setError(err.message || 'Failed to create tenant');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sm text-gray-400 animate-pulse">Loading tenants...</div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Admin</p>
            <h1 className="text-xl font-bold text-gray-900">Tenants</h1>
          </div>
          <RBACGuard permission="tenant:write" fallback={null}>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                showCreateForm
                  ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700'
              }`}
            >
              {showCreateForm ? 'Cancel' : '+ Create Tenant'}
            </button>
          </RBACGuard>
        </div>

        {/* No-permission notice */}
        <RBACGuard permission="tenant:write" fallback={
          <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
            You don't have permission to create tenants.
          </div>
        }>
          <></>
        </RBACGuard>

        {/* Create form */}
        {showCreateForm && (
          <div className="mb-6 border border-gray-200 rounded-xl p-5 bg-white shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">New Tenant</h2>
            <CreateTenantForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
            {error}
          </div>
        )}

        {/* List */}
        <div className="space-y-3">
          {tenants.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No tenants found.</div>
          ) : (
            tenants.map((tenant) => (
              <TenantCard key={tenant.id} tenant={tenant} onUpdate={loadTenants} />
            ))
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
};

const CreateTenantForm: React.FC<{
  onSubmit: (request: CreateTenantRequest) => void;
  onCancel: () => void;
}> = ({ onSubmit, onCancel }) => {
  const [name, setName] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onSubmit({ name: name.trim() });
      setName('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-3">
      <input
        type="text"
        placeholder="Tenant name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
      />
      <button
        type="submit"
        disabled={!name.trim()}
        className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors"
      >
        Create
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 text-sm font-medium bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
      >
        Cancel
      </button>
    </form>
  );
};

const TenantCard: React.FC<{ tenant: Tenant; onUpdate: () => void }> = ({ tenant, onUpdate }) => {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(tenant.name);
  const { hasPermission } = useRBAC();

  const handleUpdate = async () => {
    try {
      await tenantsApi.update(tenant.id, { name });
      setEditing(false);
      onUpdate();
    } catch (err: any) {
      alert(err.message || 'Failed to update tenant');
    }
  };

  const statusColor = tenant.status === 'active'
    ? 'bg-emerald-100 text-emerald-700'
    : 'bg-gray-100 text-gray-500';

  return (
    <div className="border border-gray-200 rounded-xl bg-white shadow-sm px-5 py-4">
      {editing ? (
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={handleUpdate}
            className="px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Save
          </button>
          <button
            onClick={() => { setEditing(false); setName(tenant.name); }}
            className="px-3 py-2 text-sm font-medium bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-gray-900 text-sm">{tenant.name}</span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusColor}`}>
                {tenant.status}
              </span>
            </div>
            <span className="text-xs text-gray-400 font-mono">{tenant.id}</span>
          </div>
          <RBACGuard permission="tenant:write" fallback={null}>
            <button
              onClick={() => setEditing(true)}
              className="px-3 py-1.5 text-xs font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
            >
              Edit
            </button>
          </RBACGuard>
        </div>
      )}
    </div>
  );
};
