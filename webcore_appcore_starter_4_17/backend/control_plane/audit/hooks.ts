/**
 * Audit Hooks
 * Guarantee audit log records both ALLOW and DENY decisions
 */

import { Request } from 'express';
import { createAuditLog, AuditLog } from './service';
import { CallerContext } from '../services/auth_context';
import { AuditAction, AuditResourceType } from '../models/audit';

/**
 * Generate request ID for correlation
 * Deterministic: use timestamp + random
 */
export function generateRequestId(): string {
  return `req_${Date.now()}_${Math.random().toString(36).substring(7)}`;
}

/**
 * Get or create request ID from request
 */
export function getRequestId(req: Request): string {
  let requestId = (req as any).requestId;
  if (!requestId) {
    requestId = req.headers['x-request-id'] as string || generateRequestId();
    (req as any).requestId = requestId;
  }
  return requestId;
}

/**
 * Audit DENY decision
 * Fail-Closed: audit write failure => throw error
 */
export function auditDeny(
  req: Request,
  context: CallerContext,
  permission: string,
  resourceType: AuditResourceType,
  resourceId: string,
  reason: string
): void {
  const requestId = getRequestId(req);

  try {
    createAuditLog({
      tenant_id: context.tenant_id,
      user_id: context.user_id,
      action: 'permission_denied',
      resource_type: resourceType,
      resource_id: resourceId,
      ip_address: req.ip || req.connection.remoteAddress,
      user_agent: req.headers['user-agent'],
      request_id: requestId,
      success: false,
      error_message: reason,
      metadata: {
        required_permission: permission,
        caller_permissions: context.permissions,
        method: req.method,
        path: req.path,
      },
    });
  } catch (error: any) {
    // Fail-Closed: audit write failure => throw error
    throw new Error(`Audit write failed: ${error.message}`);
  }
}

/**
 * Audit ALLOW decision (for mutating operations)
 * Fail-Closed: audit write failure => throw error
 */
export function auditAllow(
  req: Request,
  context: CallerContext,
  action: AuditAction,
  resourceType: AuditResourceType,
  resourceId: string
): void {
  const requestId = getRequestId(req);

  try {
    createAuditLog({
      tenant_id: context.tenant_id,
      user_id: context.user_id,
      action,
      resource_type: resourceType,
      resource_id: resourceId,
      ip_address: req.ip || req.connection.remoteAddress,
      user_agent: req.headers['user-agent'],
      request_id: requestId,
      success: true,
      metadata: {
        method: req.method,
        path: req.path,
      },
    });
  } catch (error: any) {
    // Fail-Closed: audit write failure => throw error (for mutating endpoints)
    if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) {
      throw new Error(`Audit write failed: ${error.message}`);
    }
  }
}

/**
 * Audit middleware for request ID correlation
 */
export function auditRequestIdMiddleware(
  req: Request,
  res: any,
  next: any
): void {
  getRequestId(req); // Ensure request ID is set
  next();
}

