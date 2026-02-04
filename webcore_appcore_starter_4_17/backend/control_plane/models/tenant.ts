/**
 * Tenant Model
 * Multi-tenancy foundation: every record scoped by tenant_id
 */

export interface Tenant {
  id: string;
  name: string;
  status: 'active' | 'suspended' | 'deleted';
  created_at: Date;
  updated_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateTenantRequest {
  name: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateTenantRequest {
  name?: string;
  status?: 'active' | 'suspended';
  metadata?: Record<string, unknown>;
}

