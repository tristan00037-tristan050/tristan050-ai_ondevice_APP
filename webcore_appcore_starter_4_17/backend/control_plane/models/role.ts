/**
 * Role Model
 * RBAC: Roles and permissions
 */

export type Permission = 
  | 'tenant:read'
  | 'tenant:write'
  | 'iam:tenants:list_all' // Superadmin only: list all tenants
  | 'project:read'
  | 'project:write'
  | 'environment:read'
  | 'environment:write'
  | 'user:read'
  | 'user:write'
  | 'role:read'
  | 'role:write'
  | 'audit:read'
  | 'model:read'
  | 'model:write'
  | 'model:publish';

export interface Role {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  permissions: Permission[];
  created_at: Date;
  updated_at: Date;
}

export interface CreateRoleRequest {
  tenant_id: string;
  name: string;
  description?: string;
  permissions: Permission[];
}

export interface UpdateRoleRequest {
  name?: string;
  description?: string;
  permissions?: Permission[];
}

export interface UserRoleAssignment {
  user_id: string;
  role_id: string;
  tenant_id: string;
  assigned_at: Date;
  assigned_by: string;
}

