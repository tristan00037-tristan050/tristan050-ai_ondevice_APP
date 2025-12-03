import { Request, Response, NextFunction } from 'express';

type Role = 'viewer' | 'operator' | 'auditor' | 'admin';

function parseRoleMap(): Record<string, Role> {
  try {
    const raw = process.env.OS_ROLE_MAP_JSON || '{"viewer":"viewer","operator":"operator","auditor":"auditor","admin":"admin"}';
    return JSON.parse(raw);
  } catch {
    return { viewer: 'viewer', operator: 'operator', auditor: 'auditor', admin: 'admin' };
  }
}

export function osPolicyBridge() {
  const map = parseRoleMap();
  const enforce = (process.env.OS_POLICY_BRIDGE_ENFORCE || 'true') === 'true';

  return (req: Request, res: Response, next: NextFunction) => {
    const tenant = req.header('X-Tenant') || '';
    const osRole = (req.header('X-User-Role') || '').toLowerCase();
    const role = (map as any)[osRole] as Role | undefined;

    if (enforce && (!tenant || !role)) {
      return res.status(403).json({
        error_code: 'OS_POLICY_DENY',
        request_id: (req as any).requestId || (req as any).id,
        message: 'Invalid tenant/role from OS headers',
      });
    }

    // 요청 컨텍스트(감사/로그 상관관계용)
    (req as any).ctx = {
      tenant,
      role: role || 'viewer',
      actor: req.header('X-User-Id') || '',
      purpose: req.header('X-Purpose-Of-Use') || '',
      classification: req.header('X-Data-Classification') || '',
      request_id: (req as any).requestId || (req as any).id,
    };
    next();
  };
}

