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
    return <div>Loading...</div>;
  }

  return (
    <ErrorBoundary>
      <div className="users-page">
        <h1>Users</h1>
        
        <RBACGuard permission="user:write" fallback={<p>You don't have permission to create users</p>}>
          <button onClick={() => setShowCreateForm(!showCreateForm)}>
            {showCreateForm ? 'Cancel' : 'Create User'}
          </button>
        </RBACGuard>

        {showCreateForm && (
          <CreateUserForm onSubmit={handleCreate} onCancel={() => setShowCreateForm(false)} />
        )}

        {error && <div className="error">{error}</div>}

        <div className="users-list">
          {users.map((user) => (
            <UserCard key={user.id} user={user} onUpdate={loadUsers} />
          ))}
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

  return (
    <form onSubmit={handleSubmit} className="create-user-form">
      <input
        type="text"
        placeholder="Tenant ID"
        value={tenantId}
        onChange={(e) => setTenantId(e.target.value)}
        required
      />
      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      <input
        type="text"
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <button type="submit">Create</button>
      <button type="button" onClick={onCancel}>Cancel</button>
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

  return (
    <div className="user-card">
      <h3>{user.name}</h3>
      <p>Email: {user.email}</p>
      <p>Status: {user.status}</p>
      <p>Tenant ID: {user.tenant_id}</p>
      
      <RBACGuard permission="user:write" fallback={null}>
        {editing ? (
          <div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button onClick={handleUpdate}>Save</button>
            <button onClick={() => { setEditing(false); setEmail(user.email); setName(user.name); }}>Cancel</button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)}>Edit</button>
        )}
      </RBACGuard>
    </div>
  );
};

