import { validateMetaOnly } from "../guards/meta_only_validator";

type ReqLike = { body: any };
type ResLike = { status: (c: number) => ResLike; json: (v: any) => any };
type Next = () => any;

// Apply to endpoints that accept client -> server meta payload.
// This gate blocks raw text/excerpts by schema allowlist + type/length/pattern constraints.
export function requireMetaOnly(req: ReqLike, res: ResLike, next: Next) {
  const r = validateMetaOnly(req.body);
  if (!r.ok) {
    return res.status(400).json({
      ok: false,
      reason_code: r.reason_code,
      detail: r.detail
    });
  }
  return next();
}

