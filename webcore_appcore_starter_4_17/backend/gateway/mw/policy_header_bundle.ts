import fs from "node:fs";
import path from "node:path";

type ReqLike = { headers: Record<string, any> };
type ResLike = { status: (c: number) => ResLike; json: (v: any) => any };
type Next = () => any;

function readSSOT() {
  const p = path.join(process.cwd(), "docs/ops/contracts/POLICY_HEADER_BUNDLE_SSOT.json");
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw) as {
    bundle_name: string;
    required_headers: string[];
    mode_values: string[];
  };
}

function norm(h: string) {
  return h.toLowerCase();
}

export function requirePolicyHeaderBundle(req: ReqLike, res: ResLike, next: Next) {
  const ssot = readSSOT();
  const headers = req.headers || {};
  const missing: string[] = [];

  for (const h of ssot.required_headers) {
    const key = norm(h);
    const v = headers[key];
    if (v === undefined || v === null || String(v).trim() === "") missing.push(h);
  }

  // mode validation (if present)
  const mode = String(headers["x-os-mode"] || "").toLowerCase();
  if (mode && !ssot.mode_values.includes(mode)) {
    return res.status(400).json({
      ok: false,
      reason_code: "POLICY_HEADER_INVALID_MODE",
      bundle: ssot.bundle_name,
      mode
    });
  }

  if (missing.length > 0) {
    return res.status(400).json({
      ok: false,
      reason_code: "POLICY_HEADER_MISSING",
      bundle: ssot.bundle_name,
      missing
    });
  }

  return next();
}

