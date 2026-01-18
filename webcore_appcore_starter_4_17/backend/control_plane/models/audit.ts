/**
 * Audit Log Model
 * Immutable append-only audit records
 */

export type AuditAction = 
  | 'create'
  | 'update'
  | 'delete'
  | 'read'
  | 'login'
  | 'logout'
  | 'permission_denied';

export type AuditResourceType = 
  | 'tenant'
  | 'project'
  | 'environment'
  | 'user'
  | 'role'
  | 'audit_log';

export interface AuditLog {
  id: string;
  tenant_id: string;
  user_id: string;
  action: AuditAction;
  resource_type: AuditResourceType;
  resource_id: string;
  ip_address?: string;
  user_agent?: string;
  request_id?: string;
  success: boolean;
  error_message?: string;
  metadata?: Record<string, unknown>;
  created_at: Date; // Immutable timestamp
}

export interface CreateAuditLogRequest {
  tenant_id: string;
  user_id: string;
  action: AuditAction;
  resource_type: AuditResourceType;
  resource_id: string;
  ip_address?: string;
  user_agent?: string;
  request_id?: string;
  success: boolean;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

