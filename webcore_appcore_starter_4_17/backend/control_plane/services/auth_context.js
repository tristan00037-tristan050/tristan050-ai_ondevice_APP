"use strict";
/**
 * Auth Context Service
 * Single source of truth for caller context
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.getCallerContext = getCallerContext;
exports.requireCallerContext = requireCallerContext;
exports.hasPermission = hasPermission;
exports.isSuperAdmin = isSuperAdmin;
/**
 * Extract caller context from request
 * Single source of truth: req.auth = { tenant_id, user_id, roles, permissions }
 */
function getCallerContext(req) {
    const authContext = req.authContext;
    if (!authContext) {
        return null;
    }
    // Get user roles and permissions (should be loaded from DB in real implementation)
    const userRoles = req.userRoles || [];
    const permissions = [];
    // Extract permissions from roles
    for (const role of userRoles) {
        if (role.permissions && Array.isArray(role.permissions)) {
            permissions.push(...role.permissions);
        }
    }
    return {
        tenant_id: authContext.tenant_id,
        user_id: authContext.user_id,
        roles: authContext.roles || [],
        permissions,
    };
}
/**
 * Require caller context middleware
 * Fail-Closed: no context => 401
 */
function requireCallerContext(req, res, next) {
    const context = getCallerContext(req);
    if (!context) {
        return res.status(401).json({
            error: 'Unauthorized',
            message: 'Authentication required',
        });
    }
    req.callerContext = context;
    next();
}
/**
 * Check if caller has permission
 * Fail-Closed: default deny
 */
function hasPermission(context, permission) {
    return context.permissions.includes(permission);
}
/**
 * Check if caller is superadmin
 * Superadmin has 'iam:tenants:list_all' permission
 */
function isSuperAdmin(context) {
    return hasPermission(context, 'iam:tenants:list_all');
}
