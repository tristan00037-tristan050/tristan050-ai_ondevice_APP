import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

function lockPath(name: string) {
  return path.join(DATA_DIR, `${name}.lock`);
}

export function withFileLock<T>(name: string, fn: () => T): T {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const lp = lockPath(name);

  // simple lock: create lock file exclusively
  const fd = fs.openSync(lp, "wx"); // throws if exists
  try {
    return fn();
  } finally {
    fs.closeSync(fd);
    fs.unlinkSync(lp);
  }
}

