/**
 * P6-P1-02A: Trace router wiring — local-only server
 * 목표: TRACE_ROUTER_MOUNTED=1, TRACE_ROUTER_USED=1
 * 보안: 127.0.0.1 로컬-only listen (all-interfaces 노출 금지)
 */

import express from "express";
import { buildTraceRouter } from "./routes/trace_v1";
import { join } from "path";

const app = express();
const PORT = Number(process.env.TRACE_PORT) || 9998;
const dbPath = process.env.TRACE_DB_PATH || join(process.cwd(), ".trace_db");

app.use(express.json({ limit: "32kb" }));
app.use("/trace", buildTraceRouter(dbPath));

app.listen(PORT, "127.0.0.1", () => {
  console.log(`trace server listening on 127.0.0.1:${PORT}`);
});
