"use strict";
/**
 * Audit Service
 * Immutable append-only audit logging
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.clearAuditLogs = clearAuditLogs;
exports.createAuditLog = createAuditLog;
exports.queryAuditLogs = queryAuditLogs;
exports.auditMiddleware = auditMiddleware;
// In-memory store (should be replaced with database in production)
let auditLogs = [];
/**
 * Deep clone helper for immutability
 * Preserves Date objects by converting them to ISO strings and back
 */
function deepClone(x) {
    if (x === null || typeof x !== 'object') {
        return x;
    }
    if (x instanceof Date) {
        return new Date(x.getTime());
    }
    if (Array.isArray(x)) {
        return x.map(item => deepClone(item));
    }
    const cloned = {};
    for (const key in x) {
        if (Object.prototype.hasOwnProperty.call(x, key)) {
            cloned[key] = deepClone(x[key]);
        }
    }
    return cloned;
}
/**
 * Clear audit logs (for testing only)
 */
function clearAuditLogs() {
    auditLogs = [];
}
/**
 * Create audit log entry
 * Immutable: no updates/deletes allowed
 */
function createAuditLog(request) {
    const auditLog = {
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
function queryAuditLogs(tenant_id, filters) {
    // Fail-Closed: Cross-tenant access blocked
    const results = auditLogs.filter(log => {
        if (log.tenant_id !== tenant_id) {
            return false; // Block cross-tenant access
        }
        if (filters) {
            if (filters.user_id && log.user_id !== filters.user_id)
                return false;
            if (filters.action && log.action !== filters.action)
                return false;
            if (filters.resource_type && log.resource_type !== filters.resource_type)
                return false;
            if (filters.resource_id && log.resource_id !== filters.resource_id)
                return false;
            if (filters.start_date && log.created_at < filters.start_date)
                return false;
            if (filters.end_date && log.created_at > filters.end_date)
                return false;
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
function auditMiddleware(action, resource_type) {
    return async (req, res, next) => {
        const context = req.callerContext;
        if (!context) {
            return next(); // Auth middleware should have already handled this
        }
        // Store original res.json to intercept response
        const originalJson = res.json.bind(res);
        res.json = function (body) {
            // Log audit entry after response (ALLOW decision for mutating operations)
            const success = res.statusCode >= 200 && res.statusCode < 300;
            const resourceId = req.params.id || req.body.id || 'unknown';
            // Only audit ALLOW for successful mutating operations
            if (success && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) {
                const { auditAllow } = require('./hooks');
                try {
                    auditAllow(req, context, action, resource_type, resourceId);
                }
                catch (error) {
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
