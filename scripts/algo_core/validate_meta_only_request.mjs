import fs from "fs";

function block(msg) {
  console.error(`BLOCK: ${msg}`);
  process.exit(1);
}

function loadJson(p) {
  if (!fs.existsSync(p)) block(`missing file: ${p}`);
  const s = fs.readFileSync(p, "utf8");
  try { return JSON.parse(s); } catch { block(`invalid json: ${p}`); }
}

function isPlainObject(x) {
  return x != null && typeof x === "object" && !Array.isArray(x);
}

function walk(node, allow, depth = 0, path = "$") {
  if (depth > allow.limits.max_depth) block(`max depth exceeded at ${path}`);

  if (typeof node === "string") {
    if (node.length > allow.limits.max_string_len) block(`string too long at ${path}`);
    return;
  }
  if (typeof node === "number" || typeof node === "boolean" || node == null) return;

  if (Array.isArray(node)) {
    if (node.length > allow.limits.max_array_len) block(`array too long at ${path}`);
    node.forEach((v, i) => walk(v, allow, depth + 1, `${path}[${i}]`));
    return;
  }

  if (isPlainObject(node)) {
    const keys = Object.keys(node);
    if (keys.length > allow.limits.max_object_keys) block(`too many keys at ${path}`);

    for (const k of keys) {
      const lk = String(k).toLowerCase();
      for (const pat of allow.forbidden_key_patterns) {
        if (lk.includes(String(pat).toLowerCase())) block(`forbidden key "${k}" at ${path}`);
      }
      walk(node[k], allow, depth + 1, `${path}.${k}`);
    }
    return;
  }

  block(`unsupported type at ${path}: ${typeof node}`);
}

function main() {
  const [reqPath, allowPath] = process.argv.slice(2);
  if (!reqPath || !allowPath) block("usage: node validate_meta_only_request.mjs <request.json> <allowlist.json>");

  const allow = loadJson(allowPath);
  const req = loadJson(reqPath);

  if (!isPlainObject(req)) block("request must be a JSON object");
  if (!Array.isArray(allow.allowed_root_keys)) block("allowlist.allowed_root_keys must be array");

  // root key allowlist: fail-closed
  for (const k of Object.keys(req)) {
    if (!allow.allowed_root_keys.includes(k)) block(`root key not allowed: ${k}`);
  }

  // recursive constraints + forbidden key patterns
  walk(req, allow, 0, "$");

  console.log("ALGO_META_ONLY_VALID=1");
}

main();
