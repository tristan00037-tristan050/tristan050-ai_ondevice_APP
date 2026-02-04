import fs from "fs";
import path from "path";
import crypto from "crypto";

function sha256File(p) {
  const buf = fs.readFileSync(p);
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function walk(dir, baseDir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) {
      walk(p, baseDir, out);
    } else {
      out.push(p);
    }
  }
  return out;
}

const PACK_DIR = process.argv[2] || "model_packs/accounting_v0";
const ROOT = process.cwd();
const ABS_PACK_DIR = path.join(ROOT, PACK_DIR);

if (!fs.existsSync(ABS_PACK_DIR)) {
  console.error(`BLOCK: pack directory not found: ${PACK_DIR}`);
  process.exit(1);
}

// Read pack.json
const packJsonPath = path.join(ABS_PACK_DIR, "pack.json");
if (!fs.existsSync(packJsonPath)) {
  console.error(`BLOCK: pack.json not found: ${packJsonPath}`);
  process.exit(1);
}

const packJson = JSON.parse(fs.readFileSync(packJsonPath, "utf8"));
const packName = packJson.name || path.basename(PACK_DIR);

// Collect all files (excluding manifest.json and signature.json)
const allFiles = walk(ABS_PACK_DIR, ABS_PACK_DIR);
const files = allFiles
  .filter((f) => {
    const rel = path.relative(ABS_PACK_DIR, f);
    return rel !== "manifest.json" && rel !== "signature.json";
  })
  .map((abs) => {
    const rel = path.relative(ABS_PACK_DIR, abs).replaceAll("\\", "/");
    return {
      path: rel,
      sha256: sha256File(abs),
    };
  })
  .sort((a, b) => a.path.localeCompare(b.path));

const manifest = {
  schema_name: "MODEL_PACK_MANIFEST_V0",
  pack_name: packName,
  created_at_utc: new Date().toISOString(),
  files,
};

const manifestPath = path.join(ABS_PACK_DIR, "manifest.json");
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

console.log("MODEL_PACK_MANIFEST_BUILT=1");
console.log(`MANIFEST_PATH=${manifestPath}`);

