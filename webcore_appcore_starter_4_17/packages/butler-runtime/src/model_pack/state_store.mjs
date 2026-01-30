// webcore_appcore_starter_4_17/packages/butler-runtime/src/model_pack/state_store.mjs
import fs from "node:fs";
import path from "node:path";

export function readState(statePath) {
  if (!fs.existsSync(statePath)) {
    return {
      active_pack_id: null,
      active_manifest_sha256: null,
      updated_utc: new Date(0).toISOString(),
    };
  }
  return JSON.parse(fs.readFileSync(statePath, "utf8"));
}

// tmp -> fsync(file) -> rename -> fsync(dir) (best-effort)
export function writeStateAtomicDurable(statePath, stateObj) {
  const dir = path.dirname(statePath);
  fs.mkdirSync(dir, { recursive: true });

  const tmp = path.join(dir, `.tmp.${path.basename(statePath)}.${process.pid}.${Date.now()}`);
  const data = Buffer.from(JSON.stringify(stateObj), "utf8");

  const fd = fs.openSync(tmp, "w", 0o600);
  try {
    fs.writeSync(fd, data, 0, data.length, 0);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }

  fs.renameSync(tmp, statePath);

  // dir fsync best-effort
  try {
    const dfd = fs.openSync(dir, "r");
    try { fs.fsyncSync(dfd); } finally { fs.closeSync(dfd); }
  } catch {
    // best-effort (platform/fs dependent)
  }
}

