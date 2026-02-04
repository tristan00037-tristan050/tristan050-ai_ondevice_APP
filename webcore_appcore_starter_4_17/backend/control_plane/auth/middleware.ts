/**
 * Authentication Middleware
 * Fail-Closed: no token or invalid => 401
 */

import { Request, Response, NextFunction } from 'express';
import { extractAuthContext, OIDCConfig, AuthContext } from './oidc';
import { getCallerContext, requireCallerContext } from '../services/auth_context';

// OIDC config (should be loaded from environment)
const oidcConfig: OIDCConfig = {
  issuer: process.env.OIDC_ISSUER || 'https://accounts.google.com',
  audience: process.env.OIDC_AUDIENCE || 'control-plane-api',
  jwksUri: process.env.OIDC_JWKS_URI || 'https://www.googleapis.com/oauth2/v3/certs',
};

/**
 * Require authentication middleware
 * Fail-Closed: no token or invalid => 401
 */
export async function requireAuth(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const authContext = await extractAuthContext(req, oidcConfig);
    (req as any).authContext = authContext;
    
    // Load user roles (should be loaded from DB in real implementation)
    // For now, mock based on auth context
    (req as any).userRoles = [];
    
    next();
  } catch (error: any) {
    res.status(401).json({
      error: 'Unauthorized',
      message: error.message || 'Invalid or missing token',
    });
  }
}

/**
 * Extract tenant ID from request
 * Used for multi-tenant scoping
 */
export function extractTenantId(req: Request): string | null {
  const context = getCallerContext(req);
  return context?.tenant_id || null;
}

/**
 * Require caller context (auth + context)
 */
export function requireAuthAndContext(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  requireAuth(req, res, () => {
    requireCallerContext(req, res, next);
  });
}
