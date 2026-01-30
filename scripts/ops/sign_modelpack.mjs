import fs from "fs";
import path from "path";
import crypto from "crypto";

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

const PACK_DIR = process.argv[2] || "model_packs/accounting_v0";
const ROOT = process.cwd();
const ABS_PACK_DIR = path.join(ROOT, PACK_DIR);

const manifestPath = path.join(ABS_PACK_DIR, "manifest.json");
if (!fs.existsSync(manifestPath)) {
  console.error(`BLOCK: manifest.json not found: ${manifestPath}`);
  process.exit(1);
}

const manifestJson = fs.readFileSync(manifestPath, "utf8");
const manifestBuf = Buffer.from(manifestJson, "utf8");

// Keys: allow operator-provided keys; fallback to ephemeral for dev
const pubB64 = process.env.MODEL_PACK_SIGN_PUBLIC_KEY_B64 || "";
const privB64 = process.env.MODEL_PACK_SIGN_PRIVATE_KEY_B64 || "";
const keyId = process.env.MODEL_PACK_SIGNING_KEY_ID || "";

const keys = (pubB64 && privB64) ? { publicKeyB64: pubB64, privateKeyB64: privB64 } : genKeyPair();
const finalKeyId = keyId || crypto.createHash("sha256").update(keys.publicKeyB64).digest("hex").slice(0, 16);

const sigB64 = sign(manifestBuf, keys.privateKeyB64);

// Verify signature
const ok = verify(manifestBuf, sigB64, keys.publicKeyB64);
if (!ok) {
  console.error("BLOCK: signature verify failed");
  process.exit(1);
}

const signature = {
  schema_name: "MODEL_PACK_SIGNATURE_V0",
  key_id: finalKeyId,
  signature_b64: sigB64,
  public_key_b64: keys.publicKeyB64,
  signed_at_utc: new Date().toISOString(),
};

const signaturePath = path.join(ABS_PACK_DIR, "signature.json");
fs.writeFileSync(signaturePath, JSON.stringify(signature, null, 2) + "\n");

console.log("MODEL_PACK_SIGNATURE_BUILT=1");
console.log(`SIGNATURE_PATH=${signaturePath}`);

