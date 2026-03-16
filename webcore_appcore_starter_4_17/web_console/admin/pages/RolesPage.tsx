/**
 * Roles Page
 * Manage roles (RBAC enforced)
 */

import React, { useState, useEffect } from 'react';
import { rolesApi, Role, CreateRoleRequest } from '../api_client/api';
import { RBACGuard, RBACButton, useRBAC } from '../components/RBACGuard';
import { ErrorBoundary } from '../components/ErrorBoundary';

const PERMISSIONS = [
  'tenant:read',
  'tenant:write',
  'project:read',
  'project:write',
  'environment:read',
  'environment:write',
  'user:read',
  'user:write',
  'role:read',
  'role:write',
  'audit:read',
];

const PERMISSION_COLORS: Record<string, string> = {
  'tenant:write': 'bg-indigo-100 text-indigo-700',
  'user:write': 'bg-violet-100 text-violet-700',
  'role:write': 'bg-rose-100 text-rose-700',
  'audit:read': 'bg-amber-100 text-amber-700',
};

function permColor(p: string) {
  return PERMISSION_COLORS[p] ?? 'bg-gray-100 text-gray-600';
}

export const RolesPage: React.FC = () => {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { hasPermission } = useRBAC();

  useEffect(() => {
    loadRoles();
  }, []);

  const loadRoles = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await rolesApi.list();
      setRoles(response.roles);
    } catch (err: any) {
      setError(err.message || 'Failed to load roles');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (request: CreateRoleRequest) => {
    try {
      setError(null);
      await rolesApi.create(request);
      setShowCreateForm(false);
      await loadRoles();
    } catch (err: any) {
      setError(err.message || 'Failed to create role');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sm text-gray-400 animate-pulse">Loading roles...</div>
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
            <h1 className="text-xl font-bold text-gray-900">Roles</h1>
          </div>
          <RBACGuard permission="role:write" fallback={null}>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                showCreateForm
                  ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700'
              }`}
            >
              {showCreateForm ? 'Cancel' : '+ Create Role'}
            </button>
          </RBACGuard>
        </div>

        {/* No-permission notice */}
        <RBACGuard permission="role:write" fallback={
          <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
            You don't have permission to create roles.
          </div>
        }>
          <></>
        </RBACGuard>

        {/* Create form */}
        {showCreateForm && (
          <div className="mb-6 border border-gray-200 rounded-xl p-5 bg-white shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">New Role</h2>
            <CreateRoleForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
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
          {roles.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No roles found.</div>
          ) : (
            roles.map((role) => (
              <RoleCard key={role.id} role={role} onUpdate={loadRoles} />
            ))
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
};

const CreateRoleForm: React.FC<{
  onSubmit: (request: CreateRoleRequest) => void;
  onCancel: () => void;
}> = ({ onSubmit, onCancel }) => {
  const [tenantId, setTenantId] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (tenantId.trim() && name.trim() && selectedPermissions.length > 0) {
      onSubmit({
        tenant_id: tenantId.trim(),
        name: name.trim(),
        description: description.trim() || undefined,
        permissions: selectedPermissions,
      });
      setTenantId('');
      setName('');
      setDescription('');
      setSelectedPermissions([]);
    }
  };

  const togglePermission = (permission: string) => {
    setSelectedPermissions((prev) =>
      prev.includes(permission)
        ? prev.filter((p) => p !== permission)
        : [...prev, permission]
    );
  };

  const isValid = tenantId.trim() && name.trim() && selectedPermissions.length > 0;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input
          type="text"
          placeholder="Tenant ID"
          value={tenantId}
          onChange={(e) => setTenantId(e.target.value)}
          required
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <input
          type="text"
          placeholder="Role name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>
      <textarea
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
      />
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Permissions</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {PERMISSIONS.map((permission) => (
            <label
              key={permission}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-xs ${
                selectedPermissions.includes(permission)
                  ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                  : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedPermissions.includes(permission)}
                onChange={() => togglePermission(permission)}
                className="accent-indigo-600"
              />
              {permission}
            </label>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!isValid}
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
      </div>
    </form>
  );
};

const RoleCard: React.FC<{ role: Role; onUpdate: () => void }> = ({ role, onUpdate }) => {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description || '');
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>(role.permissions);

  const handleUpdate = async () => {
    try {
      await rolesApi.update(role.id, {
        name,
        description: description || undefined,
        permissions: selectedPermissions,
      });
      setEditing(false);
      onUpdate();
    } catch (err: any) {
      alert(err.message || 'Failed to update role');
    }
  };

  return (
    <div className="border border-gray-200 rounded-xl bg-white shadow-sm px-5 py-4">
      {editing ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={1}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
            />
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Permissions</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {PERMISSIONS.map((permission) => (
                <label
                  key={permission}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-xs ${
                    selectedPermissions.includes(permission)
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                      : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedPermissions.includes(permission)}
                    onChange={() => {
                      setSelectedPermissions((prev) =>
                        prev.includes(permission)
                          ? prev.filter((p) => p !== permission)
                          : [...prev, permission]
                      );
                    }}
                    className="accent-indigo-600"
                  />
                  {permission}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleUpdate}
              className="px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Save
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setName(role.name);
                setDescription(role.description || '');
                setSelectedPermissions(role.permissions);
              }}
              className="px-3 py-2 text-sm font-medium bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="font-semibold text-gray-900 text-sm mb-0.5">{role.name}</div>
              {role.description && (
                <div className="text-xs text-gray-500">{role.description}</div>
              )}
              <div className="text-xs text-gray-400 font-mono mt-0.5">tenant: {role.tenant_id}</div>
            </div>
            <RBACGuard permission="role:write" fallback={null}>
              <button
                onClick={() => setEditing(true)}
                className="px-3 py-1.5 text-xs font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
              >
                Edit
              </button>
            </RBACGuard>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {role.permissions.map((perm) => (
              <span
                key={perm}
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${permColor(perm)}`}
              >
                {perm}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
