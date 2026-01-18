/**
 * Config Model
 * Versioned configuration with rollback support
 */

export type ConfigType = 'canary' | 'meta_guard_thresholds_frozen';
export type Environment = 'development' | 'staging' | 'production';

export interface ConfigVersion {
  id: string;
  config_type: ConfigType;
  environment: Environment;
  version: number; // Immutable version number
  content: Record<string, unknown>; // Config content (JSON)
  created_at: Date;
  created_by: string; // user_id
  tenant_id: string;
  metadata?: Record<string, unknown>;
}

export interface ConfigRelease {
  id: string;
  config_type: ConfigType;
  environment: Environment;
  version_id: string; // Points to ConfigVersion.id
  released_at: Date;
  released_by: string; // user_id
  tenant_id: string;
  status: 'active' | 'rolled_back';
  rollback_to_version_id?: string; // If rolled back, points to previous version
}

export interface CreateConfigVersionRequest {
  config_type: ConfigType;
  environment: Environment;
  content: Record<string, unknown>;
  tenant_id: string;
  metadata?: Record<string, unknown>;
}

export interface ReleaseConfigRequest {
  config_type: ConfigType;
  environment: Environment;
  version_id: string;
  tenant_id: string;
}

export interface RollbackConfigRequest {
  config_type: ConfigType;
  environment: Environment;
  to_version_id: string;
  tenant_id: string;
}

