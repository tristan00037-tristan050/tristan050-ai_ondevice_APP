/**
 * API Client
 * Communicates with SVR-01 Control Plane API (OpenAPI v1)
 */

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:3000/api/v1';

export interface Tenant {
  id: string;
  name: string;
  status: 'active' | 'suspended' | 'deleted';
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  status: 'active' | 'suspended' | 'deleted';
  oidc_sub?: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface Role {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateTenantRequest {
  name: string;
  metadata?: Record<string, unknown>;
}

export interface CreateUserRequest {
  tenant_id: string;
  email: string;
  name: string;
  oidc_sub?: string;
  metadata?: Record<string, unknown>;
}

export interface CreateRoleRequest {
  tenant_id: string;
  name: string;
  description?: string;
  permissions: string[];
}

/**
 * Get auth token from session storage (standard token storage)
 */
function getAuthToken(): string | null {
  return sessionStorage.getItem('auth_token');
}

/**
 * API request helper
 */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Unauthorized - clear token and redirect to login
      sessionStorage.removeItem('auth_token');
      throw new Error('Unauthorized');
    }
    if (response.status === 403) {
      // Forbidden - RBAC denied
      const error = await response.json().catch(() => ({ message: 'Forbidden' }));
      throw new Error(error.message || 'Forbidden');
    }
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || 'Request failed');
  }

  return response.json();
}

/**
 * Tenants API
 */
export const tenantsApi = {
  list: async (): Promise<{ tenants: Tenant[] }> => {
    return apiRequest<{ tenants: Tenant[] }>('/iam/tenants');
  },
  get: async (id: string): Promise<{ tenant: Tenant }> => {
    return apiRequest<{ tenant: Tenant }>(`/iam/tenants/${id}`);
  },
  create: async (request: CreateTenantRequest): Promise<{ tenant: Tenant }> => {
    return apiRequest<{ tenant: Tenant }>('/iam/tenants', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },
  update: async (id: string, request: Partial<CreateTenantRequest>): Promise<{ tenant: Tenant }> => {
    return apiRequest<{ tenant: Tenant }>(`/iam/tenants/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  },
};

/**
 * Users API
 */
export const usersApi = {
  list: async (): Promise<{ users: User[] }> => {
    return apiRequest<{ users: User[] }>('/iam/users');
  },
  get: async (id: string): Promise<{ user: User }> => {
    return apiRequest<{ user: User }>(`/iam/users/${id}`);
  },
  create: async (request: CreateUserRequest): Promise<{ user: User }> => {
    return apiRequest<{ user: User }>('/iam/users', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },
  update: async (id: string, request: Partial<CreateUserRequest>): Promise<{ user: User }> => {
    return apiRequest<{ user: User }>(`/iam/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  },
};

/**
 * Roles API
 */
export const rolesApi = {
  list: async (): Promise<{ roles: Role[] }> => {
    return apiRequest<{ roles: Role[] }>('/iam/roles');
  },
  get: async (id: string): Promise<{ role: Role }> => {
    return apiRequest<{ role: Role }>(`/iam/roles/${id}`);
  },
  create: async (request: CreateRoleRequest): Promise<{ role: Role }> => {
    return apiRequest<{ role: Role }>('/iam/roles', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },
  update: async (id: string, request: Partial<CreateRoleRequest>): Promise<{ role: Role }> => {
    return apiRequest<{ role: Role }>(`/iam/roles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  },
};

