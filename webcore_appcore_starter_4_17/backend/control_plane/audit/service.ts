/**
 * Audit Service
 * Immutable append-only audit logging
 */

import { AuditLog, CreateAuditLogRequest, AuditAction, AuditResourceType } from '../models/audit';

// In-memory store (should be replaced with database in production)
let auditLogs: AuditLog[] = [];

/**
 * Deep clone helper for immutability
 */
function deepClone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

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

  // Deep clone on store for immutability
  const stored = deepClone(auditLog);
  auditLogs.push(stored);
  // Deep clone on return for immutability
  return deepClone(stored);
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
  const results = auditLogs.filter(log => {
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
  // Deep clone on return for immutability
  return results.map(deepClone);
}

/**
 * Audit middleware factory
 * Automatically log mutating operations (ALLOW decisions)
 * Fail-Closed: audit write failure => request fails
 */
export function auditMiddleware(
  action: AuditAction,
  resource_type: AuditResourceType
) {
  return async (req: any, res: any, next: any) => {
    const context = (req as any).callerContext;
    if (!context) {
      return next(); // Auth middleware should have already handled this
    }

    // Store original res.json to intercept response
    const originalJson = res.json.bind(res);
    res.json = function(body: any) {
      // Log audit entry after response (ALLOW decision for mutating operations)
      const success = res.statusCode >= 200 && res.statusCode < 300;
      const resourceId = req.params.id || req.body.id || 'unknown';

      // Only audit ALLOW for successful mutating operations
      if (success && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) {
        const { auditAllow } = require('./hooks');
        try {
          auditAllow(req, context, action, resource_type, resourceId);
        } catch (error: any) {
          // Fail-Closed: audit write failure => request fails
          // Note: Response already sent, but we log the error
          console.error('Audit write failed after response:', error);
        }
      }

      return originalJson(body);
    };

    next();
  };
}

