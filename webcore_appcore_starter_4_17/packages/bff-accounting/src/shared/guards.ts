/**
 * 인증/권한 가드 미들웨어
 * 
 * @module bff-accounting/shared/guards
 */

import { Request, Response, NextFunction } from 'express';

export type Role = 'viewer' | 'operator' | 'auditor' | 'admin';

/**
 * 테넌트 인증 가드
 */
export function requireTenantAuth(req: Request, res: Response, next: NextFunction) {
  const apiKey = req.headers['x-api-key'] as string | undefined;
  const tenantId = req.headers['x-tenant'] as string | undefined;
  
  if (!apiKey || !tenantId) {
    return res.status(401).json({
      error: 'Unauthorized',
      message: 'Missing X-Api-Key or X-Tenant header',
    });
  }
  
  // TODO: 실제 API 키 검증 로직 추가
  (req as any).tenantId = tenantId;
  (req as any).apiKey = apiKey;
  
  next();
}

/**
 * 역할 기반 권한 가드
 */
export function requireRole(requiredRole: Role) {
  return (req: Request, res: Response, next: NextFunction) => {
    // TODO: 실제 역할 검증 로직 추가 (현재는 모든 인증된 사용자 허용)
    // 역할 우선순위: viewer < operator < auditor < admin
    const roleHierarchy: Record<Role, number> = {
      viewer: 1,
      operator: 2,
      auditor: 3,
      admin: 4,
    };
    
    // 임시: API 키에서 역할 추출 (예: "collector-key:operator")
    const apiKey = req.headers['x-api-key'] as string | undefined;
    const userRole: Role = (apiKey?.includes(':') ? apiKey.split(':')[1] : 'operator') as Role;
    
    if (roleHierarchy[userRole] < roleHierarchy[requiredRole]) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `Required role: ${requiredRole}, current role: ${userRole}`,
      });
    }
    
    (req as any).userRole = userRole;
    next();
  };
}


