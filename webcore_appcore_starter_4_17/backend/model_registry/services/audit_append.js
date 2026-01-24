const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

// Minimal audit append implementation (meta-only, no sensitive data)
const DATA_DIR = path.resolve(__dirname, "../data");
const MAX_BYTES = 1_000_000; // 1MB
const RETAIN_DAYS = 14;

function dayKey(ts_ms) {
  return new Date(ts_ms).toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
}

function auditFile(day) {
  return `audit_${day}.json`;
}

function persistReadJson(file) {
  const p = path.join(DATA_DIR, file);
  if (!fs.existsSync(p)) return null;
  const raw = fs.readFileSync(p, "utf8");
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`PERSIST_CORRUPTED: ${file}`);
  }
}

function persistWriteJson(file, obj) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const p = path.join(DATA_DIR, file);
  const tmp = p + ".tmp";
  const data = JSON.stringify(obj, null, 2);
  fs.writeFileSync(tmp, data, "utf8");
  if (fs.existsSync(tmp)) {
    const fd = fs.openSync(tmp, "r+");
    try {
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
  }
  if (fs.existsSync(tmp)) {
    fs.renameSync(tmp, p);
  }
}

function rotateIfNeeded(day) {
  const base = path.join(DATA_DIR, auditFile(day));
  if (!fs.existsSync(base)) return;
  const sz = fs.statSync(base).size;
  if (sz <= MAX_BYTES) return;
  const rotated = path.join(DATA_DIR, `audit_${day}.1.json`);
  try {
    fs.renameSync(base, rotated);
  } catch {}
}

function enforceRetention() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const files = fs.readdirSync(DATA_DIR).filter(f => f.startsWith("audit_") && f.endsWith(".json"));
  const cutoff = Date.now() - RETAIN_DAYS * 24 * 60 * 60 * 1000;
  for (const f of files) {
    const m = f.match(/^audit_(\d{4}-\d{2}-\d{2})/);
    if (!m) continue;
    const day = m[1];
    const ts = Date.parse(day + "T00:00:00.000Z");
    if (!Number.isFinite(ts)) continue;
    if (ts < cutoff) {
      try {
        fs.unlinkSync(path.join(DATA_DIR, f));
      } catch {}
    }
  }
}

function appendAudit(evt) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const day = dayKey(evt.ts_ms);
  enforceRetention();
  rotateIfNeeded(day);
  const file = auditFile(day);
  const list = persistReadJson(file) ?? [];
  list.push(evt);
  persistWriteJson(file, list);
}

function sha256Hex(s) {
  return crypto.createHash("sha256").update(s).digest("hex");
}

function hashActorId(raw) {
  // raw 값 자체를 저장하지 않고, 해시만 저장 (meta-only)
  return sha256Hex(raw);
}

function newEventId(seed) {
  // idempotency를 위해 결정적 seed 기반으로도 생성 가능
  return sha256Hex(seed + ":" + Date.now().toString());
}

function nowUtcIso() {
  return new Date().toISOString();
}

function appendAuditV2(evt) {
  // audit.ts가 저장하는 event 형태가 AuditEvent였다면, v2를 별도 파일로 저장하는 방식도 가능
  // 여기서는 최소 변경으로 "meta-only" 이벤트를 audit daily 파일에 함께 기록한다고 가정.
  // 민감 데이터 금지 원칙 유지.
  appendAudit({
    ts_ms: Date.parse(evt.ts_utc),
    action: evt.action,
    result: evt.outcome,
    reason_code: evt.reason_code,
    key_id: evt.target?.key_id,
    sha256: evt.target?.artifact_sha256,
    // request_id 등은 audit.ts가 확장되면 넣는다
  });
}

module.exports = { appendAuditV2, hashActorId, newEventId, nowUtcIso };

