#!/usr/bin/env bash
set -euo pipefail

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

node - <<'NODE'
const crypto = require("node:crypto");

function b64(s){ return Buffer.from(s, "utf8").toString("base64"); }

const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");

const pubPem = publicKey.export({ type: "spki", format: "pem" }).toString();
const privPem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();

// KEY_ID: 공개키 지문(sha256) 앞 16자
const pubDer = publicKey.export({ type: "spki", format: "der" });
const keyId = crypto.createHash("sha256").update(pubDer).digest("hex").slice(0, 16);

console.log("ALGO_CORE_SIGNING_KEY_ID=" + keyId);
console.log("ALGO_CORE_ALLOWED_SIGNING_KEY_IDS=" + keyId);
console.log("ALGO_CORE_SIGN_PUBLIC_KEY_B64=" + b64(pubPem));
console.log("ALGO_CORE_SIGN_PRIVATE_KEY_B64=" + b64(privPem));
NODE
