/**
 * Environment Model
 * Environments belong to projects (tenant_id + project_id scoped)
 */

export interface Environment {
  id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  type: 'development' | 'staging' | 'production';
  status: 'active' | 'archived';
  created_at: Date;
  updated_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateEnvironmentRequest {
  tenant_id: string;
  project_id: string;
  name: string;
  type: 'development' | 'staging' | 'production';
  metadata?: Record<string, unknown>;
}

export interface UpdateEnvironmentRequest {
  name?: string;
  type?: 'development' | 'staging' | 'production';
  status?: 'active' | 'archived';
  metadata?: Record<string, unknown>;
}

