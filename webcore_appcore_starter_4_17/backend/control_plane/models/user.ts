/**
 * User Model
 * Users belong to tenants (tenant_id scoped)
 */

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  status: 'active' | 'suspended' | 'deleted';
  oidc_sub?: string; // OIDC subject identifier
  created_at: Date;
  updated_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateUserRequest {
  tenant_id: string;
  email: string;
  name: string;
  oidc_sub?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateUserRequest {
  email?: string;
  name?: string;
  status?: 'active' | 'suspended';
  metadata?: Record<string, unknown>;
}

