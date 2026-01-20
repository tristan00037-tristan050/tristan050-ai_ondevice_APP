/**
 * Model Registry - ModelVersion Data Model
 * Multi-tenant: scoped by model_id (which is scoped by tenant_id)
 */

export interface ModelVersion {
  id: string;
  model_id: string;
  version: string; // semver or build identifier
  status: 'draft' | 'released' | 'rolled_back';
  created_at: Date;
  released_at?: Date;
  rolled_back_at?: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateModelVersionRequest {
  version: string;
  metadata?: Record<string, unknown>;
}

