/**
 * Model Registry - Model Data Model
 * Multi-tenant: scoped by tenant_id
 */

export interface Model {
  id: string;
  tenant_id: string;
  name: string;
  status: 'active' | 'archived' | 'deleted';
  created_at: Date;
  updated_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateModelRequest {
  name: string;
  metadata?: Record<string, unknown>;
}
