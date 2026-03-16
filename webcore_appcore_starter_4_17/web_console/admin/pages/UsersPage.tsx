/**
 * Users Page
 * Manage users (RBAC enforced)
 */

import React, { useState, useEffect } from 'react';
import { usersApi, User, CreateUserRequest } from '../api_client/api';
import { RBACGuard, RBACButton, useRBAC } from '../components/RBACGuard';
import { ErrorBoundary } from '../components/ErrorBoundary';

export const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { hasPermission } = useRBAC();

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await usersApi.list();
      setUsers(response.users);
    } catch (err: any) {
      setError(err.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (request: CreateUserRequest) => {
    try {
      setError(null);
      await usersApi.create(request);
      setShowCreateForm(false);
      await loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sm text-gray-400 animate-pulse">Loading users...</div>
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
            <h1 className="text-xl font-bold text-gray-900">Users</h1>
          </div>
          <RBACGuard permission="user:write" fallback={null}>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                showCreateForm
                  ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700'
              }`}
            >
              {showCreateForm ? 'Cancel' : '+ Create User'}
            </button>
          </RBACGuard>
        </div>

        {/* No-permission notice */}
        <RBACGuard permission="user:write" fallback={
          <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
            You don't have permission to create users.
          </div>
        }>
          <></>
        </RBACGuard>

        {/* Create form */}
        {showCreateForm && (
          <div className="mb-6 border border-gray-200 rounded-xl p-5 bg-white shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">New User</h2>
            <CreateUserForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
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
          {users.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No users found.</div>
          ) : (
            users.map((user) => (
              <UserCard key={user.id} user={user} onUpdate={loadUsers} />
            ))
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
};

const CreateUserForm: React.FC<{
  onSubmit: (request: CreateUserRequest) => void;
  onCancel: () => void;
}> = ({ onSubmit, onCancel }) => {
  const [tenantId, setTenantId] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (tenantId.trim() && email.trim() && name.trim()) {
      onSubmit({
        tenant_id: tenantId.trim(),
        email: email.trim(),
        name: name.trim(),
      });
      setTenantId('');
      setEmail('');
      setName('');
    }
  };

  const isValid = tenantId.trim() && email.trim() && name.trim();

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <input
          type="text"
          placeholder="Tenant ID"
          value={tenantId}
          onChange={(e) => setTenantId(e.target.value)}
          required
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <input
          type="text"
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
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

const UserCard: React.FC<{ user: User; onUpdate: () => void }> = ({ user, onUpdate }) => {
  const [editing, setEditing] = useState(false);
  const [email, setEmail] = useState(user.email);
  const [name, setName] = useState(user.name);

  const handleUpdate = async () => {
    try {
      await usersApi.update(user.id, { email, name });
      setEditing(false);
      onUpdate();
    } catch (err: any) {
      alert(err.message || 'Failed to update user');
    }
  };

  const statusColor = user.status === 'active'
    ? 'bg-emerald-100 text-emerald-700'
    : 'bg-gray-100 text-gray-500';

  return (
    <div className="border border-gray-200 rounded-xl bg-white shadow-sm px-5 py-4">
      {editing ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleUpdate}
              className="px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Save
            </button>
            <button
              onClick={() => { setEditing(false); setEmail(user.email); setName(user.name); }}
              className="px-3 py-2 text-sm font-medium bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <div className="flex items-start gap-4">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-semibold text-sm flex-shrink-0">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-semibold text-gray-900 text-sm">{user.name}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusColor}`}>
                  {user.status}
                </span>
              </div>
              <div className="text-xs text-gray-500">{user.email}</div>
              <div className="text-xs text-gray-400 font-mono mt-0.5">tenant: {user.tenant_id}</div>
            </div>
          </div>
          <RBACGuard permission="user:write" fallback={null}>
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
