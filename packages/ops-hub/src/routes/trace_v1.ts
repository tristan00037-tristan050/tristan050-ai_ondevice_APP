import express from "express";
import { openTraceStore } from "../store/trace_store_sql_v1";

// TRACE_BIND_MODE=LOCAL_ONLY_V1
// TRACE_AUTH_MODE=API_KEY_REQUIRED_V1
// TRACE_API_KEY_EXPECTED_TOKEN=1

export function buildTraceRouter(dbPath: string) {
  const r = express.Router();
  r.use(express.json({ limit: "32kb" }));

  const store = openTraceStore(dbPath);

  // v0: 로컬/테스트 전용(운영 노출 금지)
  r.post("/v1/trace/ingest", (req, res) => {
    const out = store.ingest(req.body);
    res.json({ ok: true, inserted: out.inserted });
  });

  r.get("/v1/trace/report", (req, res) => {
    const requestId = String(req.query.request_id ?? "");
    if (!requestId) return res.status(400).json({ ok: false, error: "request_id required" });
    const rows = store.listByRequestId(requestId);
    res.json({ ok: true, request_id: requestId, rows });
  });

  return r;
}

