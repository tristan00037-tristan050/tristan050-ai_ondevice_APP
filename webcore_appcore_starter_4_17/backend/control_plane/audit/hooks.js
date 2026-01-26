"use strict";
/**
 * Audit Hooks
 * Guarantee audit log records both ALLOW and DENY decisions
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateRequestId = generateRequestId;
exports.getRequestId = getRequestId;
exports.auditDeny = auditDeny;
exports.auditAllow = auditAllow;
exports.auditRequestIdMiddleware = auditRequestIdMiddleware;
const service_1 = require("./service");
/**
 * Generate request ID for correlation
 * Deterministic: use timestamp + random
 */
function generateRequestId() {
    return `req_${Date.now()}_${Math.random().toString(36).substring(7)}`;
}
/**
 * Get or create request ID from request
 */
function getRequestId(req) {
    let requestId = req.requestId;
    if (!requestId) {
        requestId = req.headers['x-request-id'] || generateRequestId();
        req.requestId = requestId;
    }
    return requestId;
}
/**
 * Audit DENY decision
 * Fail-Closed: audit write failure => throw error
 */
function auditDeny(req, context, permission, resourceType, resourceId, reason) {
    const requestId = getRequestId(req);
    try {
        (0, service_1.createAuditLog)({
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
    }
    catch (error) {
        // Fail-Closed: audit write failure => throw error
        throw new Error(`Audit write failed: ${error.message}`);
    }
}
/**
 * Audit ALLOW decision (for mutating operations)
 * Fail-Closed: audit write failure => throw error
 */
function auditAllow(req, context, action, resourceType, resourceId) {
    const requestId = getRequestId(req);
    try {
        (0, service_1.createAuditLog)({
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
    }
    catch (error) {
        // Fail-Closed: audit write failure => throw error (for mutating endpoints)
        if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) {
            throw new Error(`Audit write failed: ${error.message}`);
        }
    }
}
/**
 * Audit middleware for request ID correlation
 */
function auditRequestIdMiddleware(req, res, next) {
    getRequestId(req); // Ensure request ID is set
    next();
}
