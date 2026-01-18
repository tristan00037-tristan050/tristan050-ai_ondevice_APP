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
    return <div>Loading...</div>;
  }

  return (
    <ErrorBoundary>
      <div className="tenants-page">
        <h1>Tenants</h1>
        
        <RBACGuard permission="tenant:write" fallback={<p>You don't have permission to create tenants</p>}>
          <button onClick={() => setShowCreateForm(!showCreateForm)}>
            {showCreateForm ? 'Cancel' : 'Create Tenant'}
          </button>
        </RBACGuard>

        {showCreateForm && (
          <CreateTenantForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
        )}

        {error && <div className="error">{error}</div>}

        <div className="tenants-list">
          {tenants.map((tenant) => (
            <TenantCard key={tenant.id} tenant={tenant} onUpdate={loadTenants} />
          ))}
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
    <form onSubmit={handleSubmit} className="create-tenant-form">
      <input
        type="text"
        placeholder="Tenant name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <button type="submit">Create</button>
      <button type="button" onClick={onCancel}>Cancel</button>
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

  return (
    <div className="tenant-card">
      <h3>{tenant.name}</h3>
      <p>Status: {tenant.status}</p>
      <p>ID: {tenant.id}</p>
      
      <RBACGuard permission="tenant:write" fallback={null}>
        {editing ? (
          <div>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button onClick={handleUpdate}>Save</button>
            <button onClick={() => { setEditing(false); setName(tenant.name); }}>Cancel</button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)}>Edit</button>
        )}
      </RBACGuard>
    </div>
  );
};

