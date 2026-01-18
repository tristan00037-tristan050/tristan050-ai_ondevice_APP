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
    return <div>Loading...</div>;
  }

  return (
    <ErrorBoundary>
      <div className="roles-page">
        <h1>Roles</h1>
        
        <RBACGuard permission="role:write" fallback={<p>You don't have permission to create roles</p>}>
          <button onClick={() => setShowCreateForm(!showCreateForm)}>
            {showCreateForm ? 'Cancel' : 'Create Role'}
          </button>
        </RBACGuard>

        {showCreateForm && (
          <CreateRoleForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
        )}

        {error && <div className="error">{error}</div>}

        <div className="roles-list">
          {roles.map((role) => (
            <RoleCard key={role.id} role={role} onUpdate={loadRoles} />
          ))}
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

  return (
    <form onSubmit={handleSubmit} className="create-role-form">
      <input
        type="text"
        placeholder="Tenant ID"
        value={tenantId}
        onChange={(e) => setTenantId(e.target.value)}
        required
      />
      <input
        type="text"
        placeholder="Role name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <textarea
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="permissions-selector">
        <h4>Permissions:</h4>
        {PERMISSIONS.map((permission) => (
          <label key={permission}>
            <input
              type="checkbox"
              checked={selectedPermissions.includes(permission)}
              onChange={() => togglePermission(permission)}
            />
            {permission}
          </label>
        ))}
      </div>
      <button type="submit">Create</button>
      <button type="button" onClick={onCancel}>Cancel</button>
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
    <div className="role-card">
      <h3>{role.name}</h3>
      {role.description && <p>{role.description}</p>}
      <p>Tenant ID: {role.tenant_id}</p>
      <div>
        <strong>Permissions:</strong>
        <ul>
          {role.permissions.map((perm) => (
            <li key={perm}>{perm}</li>
          ))}
        </ul>
      </div>
      
      <RBACGuard permission="role:write" fallback={null}>
        {editing ? (
          <div>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="permissions-selector">
              {PERMISSIONS.map((permission) => (
                <label key={permission}>
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
                  />
                  {permission}
                </label>
              ))}
            </div>
            <button onClick={handleUpdate}>Save</button>
            <button onClick={() => { setEditing(false); setName(role.name); setDescription(role.description || ''); setSelectedPermissions(role.permissions); }}>Cancel</button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)}>Edit</button>
        )}
      </RBACGuard>
    </div>
  );
};

