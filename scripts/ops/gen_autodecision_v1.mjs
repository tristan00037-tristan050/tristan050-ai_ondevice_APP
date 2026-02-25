import fs from "node:fs";
import path from "node:path";

function loadRequiredKeysSSOT() {
  const ssotPath = path.resolve("docs/ops/contracts/AUTODECISION_REQUIRED_KEYS_V1.txt");
  const raw = fs.readFileSync(ssotPath, "utf8");
  const keys = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
  return new Set(keys);
}

function loadIgnoredFailKeysSSOT() {
  const ssotPath = path.resolve("docs/ops/contracts/AUTODECISION_IGNORED_FAIL_KEYS_V1.txt");
  const raw = fs.readFileSync(ssotPath, "utf8");
  const keys = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
  return new Set(keys);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function collectKeys(obj) {
  const keys = {};
  if (obj && typeof obj === "object") {
    if (obj.keys && typeof obj.keys === "object") Object.assign(keys, obj.keys);
    if (Array.isArray(obj.results)) {
      for (const r of obj.results) {
        if (r && r.keys && typeof r.keys === "object") Object.assign(keys, r.keys);
      }
    }
  }
  return keys;
}

function main() {
  const repoPath = "docs/ops/reports/repo_contracts_latest.json";
  const aiPath = "docs/ops/reports/ai_smoke_latest.json";
  const outJson = "docs/ops/reports/autodecision_latest.json";
  const outMd = "docs/ops/reports/autodecision_latest.md";

  if (!fs.existsSync(repoPath)) throw new Error("BLOCK: missing " + repoPath);
  if (!fs.existsSync(aiPath)) throw new Error("BLOCK: missing " + aiPath);

  const repo = readJson(repoPath);
  const ai = readJson(aiPath);

  const repoKeys = collectKeys(repo);
  const aiKeys = collectKeys(ai);

  // 모든 키 집합(충돌 포함)
  const keySet = new Set([...Object.keys(repoKeys), ...Object.keys(aiKeys)]);

  // If onprem strict proof is skipped, do not treat SSOT-listed keys as failures.
  const ignoredFailKeysFromSSOT = loadIgnoredFailKeysSSOT();
  const ignoredFailKeys =
    String(repoKeys["ONPREM_PROOF_STRICT_SKIPPED"]) === "1"
      ? new Set(ignoredFailKeysFromSSOT)
      : new Set();

  const requiredKeys = loadRequiredKeysSSOT();

  // ignoredCount: keySet 중 requiredKeys 밖(기존 의미 유지)
  let ignoredCount = 0;
  for (const k of keySet) {
    if (!requiredKeys.has(k)) ignoredCount++;
  }

  // required 중심 평가: requiredKeys 전체를 반드시 검사
  const fails = [];
  let missingRequiredCount = 0;

  for (const k of requiredKeys) {
    const rv = repoKeys[k];
    const av = aiKeys[k];

    // presence: required 키가 두 입력 모두에 없으면 실패 (키 이름 그대로 reason_codes)
    const absent = (v) => v === undefined || v === null || v === "";
    if (absent(rv) && absent(av)) {
      missingRequiredCount++;
      fails.push(k);
      continue;
    }

    if (ignoredFailKeys.has(k)) continue;

    // 정책: "입력들 중 하나라도 non-1이면 block"
    const repoFail = (rv !== undefined) && (String(rv) !== "1");
    const aiFail = (av !== undefined) && (String(av) !== "1");
    if (repoFail || aiFail) fails.push(k);
  }
  fails.sort();

  const decision = fails.length === 0 ? "ok" : "block";
  const reason_codes = fails.slice(0, 10); // code-only

  const ts_utc = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

  const payload = {
    schema: "autodecision_v1",
    ts_utc,
    decision,
    reason_codes,
    autodecision_decision: decision,
    autodecision_reason_codes: reason_codes,
    autodecision_required_keys_count: requiredKeys.size,
    autodecision_ignored_keys_count: ignoredCount,
    autodecision_missing_required_keys_count: missingRequiredCount,
    inputs: {
      repo_contracts_latest_json: repoPath,
      ai_smoke_latest_json: aiPath
    }
  };

  fs.mkdirSync("docs/ops/reports", { recursive: true });
  fs.writeFileSync(outJson, JSON.stringify(payload));
  fs.writeFileSync(
    outMd,
    [
      "# Auto Decision (latest)",
      "",
      `- ts_utc: ${ts_utc}`,
      `- decision: ${decision}`,
      "",
      "## reason_codes (max 10)",
      ...reason_codes.map((x) => `- ${x}`),
      "",
      "## inputs",
      `- ${repoPath}`,
      `- ${aiPath}`
    ].join("\n")
  );
}

main();
