import fs from "fs";
import path from "path";
import crypto from "crypto";

function sha256File(p) {
  const buf = fs.readFileSync(p);
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

// Ed25519 sign/verify using node:crypto (same primitive used in model_registry signing.ts)
function genKeyPair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  return {
    publicKeyB64: Buffer.from(publicKey.export({ type: "spki", format: "pem" })).toString("base64"),
    privateKeyB64: Buffer.from(privateKey.export({ type: "pkcs8", format: "pem" })).toString("base64"),
  };
}
function sign(dataBuf, privateKeyB64) {
  const pem = Buffer.from(privateKeyB64, "base64").toString("utf8");
  const key = crypto.createPrivateKey({ key: pem, format: "pem", type: "pkcs8" });
  return crypto.sign(null, dataBuf, key).toString("base64");
}
function verify(dataBuf, sigB64, publicKeyB64) {
  const pem = Buffer.from(publicKeyB64, "base64").toString("utf8");
  const key = crypto.createPublicKey({ key: pem, format: "pem", type: "spki" });
  return crypto.verify(null, dataBuf, key, Buffer.from(sigB64, "base64"));
}

const ROOT = process.cwd();
const OUTDIR = path.join(ROOT, "dist");
fs.mkdirSync(OUTDIR, { recursive: true });

const targets = [
  "webcore_appcore_starter_4_17/docker-compose.yml",
  "webcore_appcore_starter_4_17/docs/ONPREM_COMPOSE_QUICKSTART.md",
  "webcore_appcore_starter_4_17/helm/onprem-gateway",
  "webcore_appcore_starter_4_17/docs/ONPREM_HELM_DEPLOYMENT.md",
];

const files = [];
for (const t of targets) {
  const p = path.join(ROOT, t);
  if (!fs.existsSync(p)) {
    console.error(`BLOCK: missing target: ${t}`);
    process.exit(1);
  }
  const st = fs.statSync(p);
  if (st.isDirectory()) files.push(...walk(p));
  else files.push(p);
}

const manifest = {
  version: new Date().toISOString().slice(0, 10),
  created_at_utc: new Date().toISOString(),
  files: files
    .map((abs) => {
      const rel = path.relative(ROOT, abs).replaceAll("\\", "/");
      return { path: rel, sha256: sha256File(abs) };
    })
    .sort((a, b) => a.path.localeCompare(b.path)),
};

const manifestJson = Buffer.from(JSON.stringify(manifest, null, 2), "utf8");

// keys: allow operator-provided keys; fallback to ephemeral keypair for self-check
const pubB64 = process.env.ONPREM_BUNDLE_SIGN_PUBLIC_KEY_B64 || "";
const privB64 = process.env.ONPREM_BUNDLE_SIGN_PRIVATE_KEY_B64 || "";
const keys = (pubB64 && privB64) ? { publicKeyB64: pubB64, privateKeyB64: privB64 } : genKeyPair();

const sigB64 = sign(manifestJson, keys.privateKeyB64);
const ok = verify(manifestJson, sigB64, keys.publicKeyB64);
if (!ok) {
  console.error("BLOCK: signature verify failed");
  process.exit(1);
}

const outManifest = path.join(OUTDIR, "onprem_bundle_manifest.json");
const outSig = path.join(OUTDIR, "onprem_bundle_manifest.sig.b64");
fs.writeFileSync(outManifest, manifestJson);
fs.writeFileSync(outSig, sigB64 + "\n");

console.log("ONPREM_SIGNED_BUNDLE_OK=1");
console.log(`BUNDLE_MANIFEST=${outManifest}`);
console.log(`BUNDLE_SIGNATURE_B64=${outSig}`);
console.log(`PUBLIC_KEY_B64=${keys.publicKeyB64}`);
