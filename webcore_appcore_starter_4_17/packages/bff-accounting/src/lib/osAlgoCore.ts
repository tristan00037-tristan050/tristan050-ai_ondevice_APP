import crypto from "node:crypto";

type Allow = {
  allowed_root_keys: string[];
  forbidden_key_patterns: string[];
  limits: {
    max_string_len: number;
    max_array_len: number;
    max_object_keys: number;
    max_depth: number;
  };
};

const ALLOW: Allow = {
  allowed_root_keys: [
    "request_id",
    "intent",
    "model_id",
    "device_class",
    "client_version",
    "constraints",
    "ts_utc",
  ],
  forbidden_key_patterns: ["prompt", "raw", "content", "text", "message", "messages", "input", "context"],
  limits: { max_string_len: 256, max_array_len: 50, max_object_keys: 50, max_depth: 6 },
};

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return x !== null && typeof x === "object" && !Array.isArray(x);
}

export function validateMetaOnlyOrThrow(body: unknown) {
  if (!isPlainObject(body)) throw new Error("META_ONLY_REQUEST_NOT_OBJECT");

  // root allowlist (fail-closed)
  for (const k of Object.keys(body)) {
    if (!ALLOW.allowed_root_keys.includes(k)) throw new Error(`META_ONLY_ROOT_KEY_NOT_ALLOWED:${k}`);
  }

  // forbidden key patterns + limits (recursive)
  const walk = (node: unknown, depth: number, path: string) => {
    if (depth > ALLOW.limits.max_depth) throw new Error(`META_ONLY_MAX_DEPTH_EXCEEDED:${path}`);

    if (typeof node === "string") {
      if (node.length > ALLOW.limits.max_string_len) throw new Error(`META_ONLY_STRING_TOO_LONG:${path}`);
      return;
    }
    if (typeof node === "number" || typeof node === "boolean" || node === null || node === undefined) return;

    if (Array.isArray(node)) {
      if (node.length > ALLOW.limits.max_array_len) throw new Error(`META_ONLY_ARRAY_TOO_LONG:${path}`);
      node.forEach((v, i) => walk(v, depth + 1, `${path}[${i}]`));
      return;
    }

    if (isPlainObject(node)) {
      const keys = Object.keys(node);
      if (keys.length > ALLOW.limits.max_object_keys) throw new Error(`META_ONLY_TOO_MANY_KEYS:${path}`);

      for (const k of keys) {
        const lk = String(k).toLowerCase();
        for (const pat of ALLOW.forbidden_key_patterns) {
          if (lk.includes(String(pat).toLowerCase())) throw new Error(`META_ONLY_FORBIDDEN_KEY:${path}.${k}`);
        }
        walk(node[k], depth + 1, `${path}.${k}`);
      }
      return;
    }

    throw new Error(`META_ONLY_UNSUPPORTED_TYPE:${path}`);
  };

  walk(body, 0, "$");

  // required fields (minimal)
  const req = body as any;
  if (!String(req.request_id || "")) throw new Error("META_ONLY_MISSING:request_id");
  if (!String(req.intent || "")) throw new Error("META_ONLY_MISSING:intent");
  if (!String(req.model_id || "")) throw new Error("META_ONLY_MISSING:model_id");
}

export function generateThreeBlocks(metaReq: any) {
  const meta = {
    request_id: String(metaReq.request_id || ""),
    intent: String(metaReq.intent || ""),
    model_id: String(metaReq.model_id || ""),
    device_class: String(metaReq.device_class || ""),
    client_version: String(metaReq.client_version || ""),
    ts_utc: String(metaReq.ts_utc || ""),
  };

  const blocks = {
    block_1_policy: {
      kind: "policy",
      meta,
      rules: ["meta-only input required", "no raw prompt/text/content accepted", "fail-closed on unknown keys"],
    },
    block_2_plan: {
      kind: "plan",
      meta,
      steps: ["validate meta schema", "generate deterministic blocks", "emit signed manifest for artifacts"],
    },
    block_3_checks: {
      kind: "checks",
      meta,
      checks: ["forbidden keys absent", "exactly 3 blocks present", "latency recorded"],
    },
  };

  return blocks;
}

// Ed25519 signer (dev: ephemeral ok / prod: must be provided)
type Signer = {
  mode: "dev" | "prod";
  keyId?: string;
  publicKeyB64: string;    // PEM(spki) base64
  privateKeyB64: string;   // PEM(pkcs8) base64
};

let CACHED: Signer | null = null;

function genKeyPair(): { publicKeyB64: string; privateKeyB64: string } {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  return {
    publicKeyB64: Buffer.from(publicKey.export({ type: "spki", format: "pem" })).toString("base64"),
    privateKeyB64: Buffer.from(privateKey.export({ type: "pkcs8", format: "pem" })).toString("base64"),
  };
}

export function getAlgoCoreSignerOrThrow(): Signer {
  if (CACHED) return CACHED;

  const mode = (process.env.ALGO_CORE_MODE || "dev").trim() === "prod" ? "prod" : "dev";
  const keyId = (process.env.ALGO_CORE_SIGNING_KEY_ID || "").trim();
  const allowIds = (process.env.ALGO_CORE_ALLOWED_SIGNING_KEY_IDS || "")
    .split(",").map((s) => s.trim()).filter(Boolean);

  const pub = (process.env.ALGO_CORE_SIGN_PUBLIC_KEY_B64 || "").trim();
  const priv = (process.env.ALGO_CORE_SIGN_PRIVATE_KEY_B64 || "").trim();

  if (mode === "prod") {
    if (!pub || !priv) throw new Error("ALGO_CORE_PROD_KEYS_REQUIRED_FAILCLOSED");
    if (!keyId) throw new Error("ALGO_CORE_PROD_KEY_ID_REQUIRED_FAILCLOSED");
    if (allowIds.length < 1) throw new Error("ALGO_CORE_PROD_KEY_ID_ALLOWLIST_REQUIRED_FAILCLOSED");
    if (!allowIds.includes(keyId)) throw new Error("ALGO_CORE_PROD_KEY_ID_NOT_ALLOWED_FAILCLOSED");
    CACHED = { mode, keyId, publicKeyB64: pub, privateKeyB64: priv };
    return CACHED;
  }

  // dev
  if (pub && priv) {
    CACHED = { mode, keyId: keyId || undefined, publicKeyB64: pub, privateKeyB64: priv };
    return CACHED;
  }

  const kp = genKeyPair();
  CACHED = { mode, publicKeyB64: kp.publicKeyB64, privateKeyB64: kp.privateKeyB64 };
  return CACHED;
}

export function signManifest(payload: unknown) {
  const signer = getAlgoCoreSignerOrThrow();
  const json = Buffer.from(JSON.stringify(payload), "utf8");

  const pemPriv = Buffer.from(signer.privateKeyB64, "base64").toString("utf8");
  const pemPub = Buffer.from(signer.publicKeyB64, "base64").toString("utf8");

  const privKey = crypto.createPrivateKey({ key: pemPriv, format: "pem", type: "pkcs8" });
  const pubKey = crypto.createPublicKey({ key: pemPub, format: "pem", type: "spki" });

  const sigB64 = crypto.sign(null, json, privKey).toString("base64");
  const ok = crypto.verify(null, json, pubKey, Buffer.from(sigB64, "base64"));
  if (!ok) throw new Error("ALGO_CORE_SIGNATURE_VERIFY_FAILED_FAILCLOSED");

  const sha256 = crypto.createHash("sha256").update(json).digest("hex");

  return {
    manifest_sha256: sha256,
    signature_b64: sigB64,
    public_key_b64: signer.publicKeyB64,
    key_id: signer.keyId || undefined,
    mode: signer.mode,
  };
}
