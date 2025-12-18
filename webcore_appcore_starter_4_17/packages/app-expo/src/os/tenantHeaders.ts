export type TenantHeadersInput = {
  tenantId: string;
  userId?: string;
  userRole?: string;
  apiKey?: string;
};

/**
 * Enterprise Gateway Header Policy (Playbook P5)
 * - Always send X-Tenant / X-User-Id / X-User-Role
 */
export function buildTenantHeaders(
  cfg: TenantHeadersInput
): Record<string, string> {
  return {
    "X-Tenant": cfg.tenantId,
    "X-User-Id": cfg.userId ?? "hud-user-1",
    "X-User-Role": cfg.userRole ?? "operator",
    "X-Api-Key": cfg.apiKey ?? "collector-key:operator",
  };
}

