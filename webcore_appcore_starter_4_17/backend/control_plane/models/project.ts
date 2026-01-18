/**
 * Project Model
 * Projects belong to tenants (tenant_id scoped)
 */

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  status: 'active' | 'archived';
  created_at: Date;
  updated_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateProjectRequest {
  tenant_id: string;
  name: string;
  description?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  status?: 'active' | 'archived';
  metadata?: Record<string, unknown>;
}

