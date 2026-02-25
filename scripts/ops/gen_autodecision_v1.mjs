import fs from "node:fs";

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
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

  // ONPREM_PROOF_STRICT 스킵 시 해당 proof 키는 평가 제외 (착시 block 방지)
  const onpremStrictSkipped = String(repoKeys["ONPREM_PROOF_STRICT_SKIPPED"]) === "1";
  const skipOnpremProofKeys = onpremStrictSkipped
    ? new Set(["ONPREM_REAL_WORLD_PROOF_OK", "ONPREM_REAL_WORLD_PROOF_FORMAT_OK"])
    : new Set();

  const fails = [];
  for (const k of keySet) {
    const rv = repoKeys[k];
    const av = aiKeys[k];

    // *_SKIPPED 키는 평가 대상에서 제외 (상태 키로 인한 착시 block 방지)
    if (k.endsWith("_SKIPPED")) continue;
    if (skipOnpremProofKeys.has(k)) continue;

    // 정책: "입력들 중 하나라도 non-1이면 block"
    const repoFail = (rv !== undefined) && (String(rv) !== "1");
    const aiFail   = (av !== undefined) && (String(av) !== "1");

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
