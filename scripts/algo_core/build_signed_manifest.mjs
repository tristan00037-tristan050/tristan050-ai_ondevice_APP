import fs from "fs";
import path from "path";
import crypto from "crypto";

function block(msg) {
  console.error(`BLOCK: ${msg}`);
  process.exit(1);
}

function sha256File(p) {
  const buf = fs.readFileSync(p);
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function genKeyPair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  return {
    publicKeyB64: Buffer.from(publicKey.export({ type: "spki", format: "pem" })).toString("base64"),
    privateKeyB64: Buffer.from(privateKey.export({ type: "pkcs8", format: "pem" })).toString("base64")
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

function main() {
  const ROOT = process.cwd();
  const OUTDIR = path.join(ROOT, "dist");
  fs.mkdirSync(OUTDIR, { recursive: true });

  const targets = [
    "scripts/algo_core/meta_only_allowlist.json",
    "scripts/algo_core/sample_meta_request.json",
    "scripts/algo_core/validate_meta_only_request.mjs",
    "scripts/algo_core/generate_three_blocks.mjs",
    "docs/ops/contracts/ALGO_CORE_P95_BUDGET_SSOT.json",
    "docs/ops/contracts/ALGO_CORE_DELIVERED_KEYS_SSOT.md"
  ];

  for (const rel of targets) {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) block(`missing target: ${rel}`);
    if (!fs.statSync(abs).isFile()) block(`target must be file: ${rel}`);
  }

  const manifest = {
    schema_name: "ALGO_CORE_SIGNED_MANIFEST_V1",
    created_at_utc: new Date().toISOString(),
    files: targets.map((rel) => ({ path: rel, sha256: sha256File(path.join(ROOT, rel)) }))
  };

  const manifestBuf = Buffer.from(JSON.stringify(manifest, null, 2), "utf8");
  const keys = genKeyPair();
  const sigB64 = sign(manifestBuf, keys.privateKeyB64);

  if (!verify(manifestBuf, sigB64, keys.publicKeyB64)) block("signature verify failed");

  // tamper test: 1바이트라도 바뀌면 verify는 반드시 실패해야 함
  const tampered = Buffer.from(manifestBuf);
  tampered[0] = (tampered[0] + 1) % 256;
  if (verify(tampered, sigB64, keys.publicKeyB64)) block("tamper verify unexpectedly succeeded");

  const outManifest = path.join(OUTDIR, "algo_core_manifest.json");
  const outSig = path.join(OUTDIR, "algo_core_manifest.sig.b64");

  fs.writeFileSync(outManifest, manifestBuf);
  fs.writeFileSync(outSig, sigB64 + "\n");

  console.log("ALGO_SIGNED_MANIFEST_BUILT=1");
  console.log(`ALGO_MANIFEST=${outManifest}`);
  console.log(`ALGO_SIGNATURE_B64=${outSig}`);
  console.log(`ALGO_PUBLIC_KEY_B64=${keys.publicKeyB64}`);
}

main();
