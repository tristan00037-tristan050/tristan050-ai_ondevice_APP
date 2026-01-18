/**
 * Audit Service
 * Immutable append-only audit logging
 */

import { AuditLog, CreateAuditLogRequest, AuditAction, AuditResourceType } from '../models/audit';

// In-memory store (should be replaced with database in production)
let auditLogs: AuditLog[] = [];

/**
 * Clear audit logs (for testing only)
 */
export function clearAuditLogs(): void {
  auditLogs = [];
}

/**
 * Create audit log entry
 * Immutable: no updates/deletes allowed
 */
export function createAuditLog(request: CreateAuditLogRequest): AuditLog {
  const auditLog: AuditLog = {
    id: `audit_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    tenant_id: request.tenant_id,
    user_id: request.user_id,
    action: request.action,
    resource_type: request.resource_type,
    resource_id: request.resource_id,
    ip_address: request.ip_address,
    user_agent: request.user_agent,
    request_id: request.request_id,
    success: request.success,
    error_message: request.error_message,
    metadata: request.metadata,
    created_at: new Date(), // Immutable timestamp
  };

  auditLogs.push(auditLog);
  return auditLog;
}

/**
 * Query audit logs
 * Fail-Closed: cross-tenant access blocked
 */
export function queryAuditLogs(
  tenant_id: string,
  filters?: {
    user_id?: string;
    action?: AuditAction;
    resource_type?: AuditResourceType;
    resource_id?: string;
    start_date?: Date;
    end_date?: Date;
  }
): AuditLog[] {
  // Fail-Closed: Cross-tenant access blocked
  return auditLogs.filter(log => {
    if (log.tenant_id !== tenant_id) {
      return false; // Block cross-tenant access
    }
    if (filters) {
      if (filters.user_id && log.user_id !== filters.user_id) return false;
      if (filters.action && log.action !== filters.action) return false;
      if (filters.resource_type && log.resource_type !== filters.resource_type) return false;
      if (filters.resource_id && log.resource_id !== filters.resource_id) return false;
      if (filters.start_date && log.created_at < filters.start_date) return false;
      if (filters.end_date && log.created_at > filters.end_date) return false;
    }
    return true;
  });
}

/**
 * Audit middleware factory
 * Automatically log mutating operations
 */
export function auditMiddleware(
  action: AuditAction,
  resource_type: AuditResourceType
) {
  return async (req: any, res: any, next: any) => {
    const authContext = (req as any).authContext;
    if (!authContext) {
      return next(); // Auth middleware should have already handled this
    }

    // Store original res.json to intercept response
    const originalJson = res.json.bind(res);
    res.json = function(body: any) {
      // Log audit entry after response
      const success = res.statusCode >= 200 && res.statusCode < 300;
      const resourceId = req.params.id || req.body.id || 'unknown';

      createAuditLog({
        tenant_id: authContext.tenant_id,
        user_id: authContext.user_id,
        action,
        resource_type,
        resource_id: resourceId,
        ip_address: req.ip || req.connection.remoteAddress,
        user_agent: req.headers['user-agent'],
        request_id: req.headers['x-request-id'],
        success,
        error_message: success ? undefined : body.error || body.message,
        metadata: {
          method: req.method,
          path: req.path,
          status_code: res.statusCode,
        },
      });

      return originalJson(body);
    };

    next();
  };
}

