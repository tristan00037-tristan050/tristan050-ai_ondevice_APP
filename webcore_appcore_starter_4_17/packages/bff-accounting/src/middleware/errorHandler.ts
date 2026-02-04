import type { ErrorRequestHandler } from "express";

/**
 * Minimal error handler for dev/QA.
 * - Logs stack to server console (no sensitive request body logging)
 * - Returns JSON 500 by default
 */
export const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  const anyErr = err as any;
  const status =
    (typeof anyErr?.status === "number" && anyErr.status) ||
    (typeof anyErr?.statusCode === "number" && anyErr.statusCode) ||
    500;

  const message =
    typeof anyErr?.message === "string" && anyErr.message.length > 0
      ? anyErr.message
      : "internal_error";

  console.error("[bff-accounting] error", {
    status,
    message,
    stack: anyErr?.stack,
  });

  if (res.headersSent) return;
  res.status(status).json({ ok: false, error: "internal_error", message });
};
