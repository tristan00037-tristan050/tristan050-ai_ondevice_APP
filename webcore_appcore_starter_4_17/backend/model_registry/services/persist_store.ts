import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

function ensureDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

export function persistWriteJson(file: string, obj: unknown) {
  ensureDir();
  const p = path.join(DATA_DIR, file);
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf8");
}

export function persistReadJson<T>(file: string): T | null {
  ensureDir();
  const p = path.join(DATA_DIR, file);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8")) as T;
}

