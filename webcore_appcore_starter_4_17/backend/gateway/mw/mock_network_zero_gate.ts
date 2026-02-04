type ReqLike = { headers: Record<string, any> };
type ResLike = { status: (c: number) => ResLike; json: (v: any) => any };
type Next = () => any;

export function forbidMockModeNetwork(req: ReqLike, res: ResLike, next: Next) {
  const mode = String(req.headers["x-os-mode"] || "").toLowerCase();

  // If mode is explicitly mock, this request must never reach server.
  if (mode === "mock") {
    return res.status(400).json({
      ok: false,
      reason_code: "MOCK_MODE_NETWORK_FORBIDDEN"
    });
  }

  return next();
}

