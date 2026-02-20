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

  const all = { ...collectKeys(repo), ...collectKeys(ai) };
  const fails = Object.entries(all)
    .filter(([_, v]) => String(v) !== "1")
    .map(([k]) => k)
    .sort();

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
