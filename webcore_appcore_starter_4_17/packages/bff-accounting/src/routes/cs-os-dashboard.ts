/**
 * CS OS Dashboard (Build-safe stub)
 * - Dev/QA build unblocker
 * - Does NOT process or log any original ticket text
 *
 * NOTE: Replace with real summarize wiring later.
 */
import { Router } from "express";
import { requireTenantAuth } from "../shared/guards.js";

export const csOsDashboardRouter = Router();

/**
 * GET /v1/cs/os/dashboard (mounted)
 */
csOsDashboardRouter.get("/", requireTenantAuth, async (req, res) => {
  const tenant =
    (req as any).tenantId ||
    (req.headers["x-tenant"] as string) ||
    (req.query.tenantId as string) ||
    "default";

  return res.status(200).json({
    ok: true,
    tenant,
    summary: "",
    suggestionLength: 0,
    items: [],
  });
});

/**
 * POST /v1/cs/os/dashboard (optional compatibility)
 */
csOsDashboardRouter.post("/", requireTenantAuth, async (req, res) => {
  const tenant =
    (req as any).tenantId ||
    (req.headers["x-tenant"] as string) ||
    (req.body?.tenantId as string) ||
    "default";

  return res.status(200).json({
    ok: true,
    tenant,
    summary: "",
    suggestionLength: 0,
    items: [],
  });
});

export default csOsDashboardRouter;
