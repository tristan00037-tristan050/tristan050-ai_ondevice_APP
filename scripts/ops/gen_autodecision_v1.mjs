import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

function loadRequiredKeysSSOT() {
  const ssotPath = path.resolve("docs/ops/contracts/AUTODECISION_REQUIRED_KEYS_V1.txt");
  const raw = fs.readFileSync(ssotPath, "utf8");
  // Inline # strip + trim (match hygiene verifier and loadIgnoredFailKeysSSOT)
  const keys = raw
    .split(/\r?\n/)
    .map((l) => l.replace(/#.*$/, "").trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
  return new Set(keys);
}

function loadIgnoredFailKeysSSOT() {
  const ssotPath = path.resolve("docs/ops/contracts/AUTODECISION_IGNORED_FAIL_KEYS_V1.txt");
  const raw = fs.readFileSync(ssotPath, "utf8");
  const lines = raw.split(/\r?\n/);
  // Inline # strip + trim; empty skip; strict key format or throw
  const keys = lines
    .map((l) => {
      const cleaned = l.replace(/#.*$/, "").trim();
      if (!cleaned) return null;
      if (!/^[A-Z0-9_]+$/.test(cleaned)) {
        throw new Error(`IGNORED_FAIL_KEYS_SSOT_INVALID_KEY:${cleaned}`);
      }
      return cleaned;
    })
    .filter(Boolean);
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

function writeExternalBytes({ repoRoot, evidenceRoot, output, payload }) {
  const writer = path.join(repoRoot, "scripts/ops/external_atomic_io.py");
  const result = spawnSync(
    "python3",
    [
      writer,
      "--repo-root", repoRoot,
      "--evidence-root", evidenceRoot,
      "--output", output,
      "--max-payload-bytes", String(16 * 1024 * 1024),
    ],
    {
      cwd: repoRoot,
      encoding: "utf8",
      input: payload,
      maxBuffer: 64 * 1024,
      windowsHide: true,
    },
  );
  if (result.status !== 0) {
    throw new Error("EXTERNAL_WRITER_FAILED");
  }
}

function writeAutodecisionOutputs({
  repoRoot,
  evidenceRoot,
  outJson,
  outMd,
  jsonBytes,
  markdownBytes,
}) {
  if (evidenceRoot) {
    writeExternalBytes({
      repoRoot,
      evidenceRoot,
      output: outJson,
      payload: jsonBytes,
    });
    writeExternalBytes({
      repoRoot,
      evidenceRoot,
      output: outMd,
      payload: markdownBytes,
    });
    return;
  }

  // Compatibility path for non-AC25 workflows that intentionally publish
  // repository reports. AC25 execution can never reach this branch.
  fs.writeFileSync(outJson, jsonBytes, { mode: 0o600 });
  fs.writeFileSync(outMd, markdownBytes, { mode: 0o600 });
}

function main() {
  const repoRoot = path.resolve(".");
  const legacyReportsRoot = process.env.AUTODECISION_REPORTS_ROOT;
  const inputReportsRoot = path.resolve(
    process.env.AUTODECISION_INPUT_REPORTS_ROOT
      || legacyReportsRoot
      || "docs/ops/reports",
  );
  const evidenceRootRaw = process.env.AC25_EVIDENCE_ROOT || "";
  const evidenceRoot = evidenceRootRaw ? path.resolve(evidenceRootRaw) : "";
  const configuredOutputRoot = process.env.AUTODECISION_OUTPUT_REPORTS_ROOT || "";
  if (evidenceRoot && !configuredOutputRoot) {
    throw new Error("AUTODECISION_OUTPUT_ROOT_REQUIRED");
  }
  const outputReportsRoot = path.resolve(
    configuredOutputRoot || legacyReportsRoot || "docs/ops/reports",
  );

  const repoPath = path.join(inputReportsRoot, "repo_contracts_latest.json");
  const repoFallback = path.join(repoRoot, "docs/ops/reports/repo_contracts_latest.json");
  const repoPathResolved = fs.existsSync(repoPath) ? repoPath : repoFallback;
  const allowDocsRepoFallback = process.env.AUTODECISION_ALLOW_DOCS_REPO_FALLBACK === "1";
  const maxAgeSec = Number(process.env.AUTODECISION_DOCS_REPO_FALLBACK_MAX_AGE_SEC || "3600"); // default 1h
  let repoFallbackUsed = 0;

  // If reportsRoot is non-default and repoPath is missing, do NOT silently fall back unless explicitly allowed.
  if (!fs.existsSync(repoPath) && (evidenceRoot || !allowDocsRepoFallback)) {
    throw new Error("BLOCK: missing " + repoPath + " (docs fallback disabled; set AUTODECISION_ALLOW_DOCS_REPO_FALLBACK=1 only for controlled pre-report runs)");
  }

  // If we will use docs fallback, enforce freshness window to avoid stale decisions.
  if (!fs.existsSync(repoPath) && allowDocsRepoFallback) {
    if (!fs.existsSync(repoPathResolved)) throw new Error("BLOCK: docs fallback file missing: " + repoPathResolved);
    const st = fs.statSync(repoPathResolved);
    const ageSec = (Date.now() - st.mtimeMs) / 1000;
    if (Number.isFinite(maxAgeSec) && ageSec > maxAgeSec) {
      throw new Error("BLOCK: docs repo_contracts_latest.json is stale (age_sec=" + Math.floor(ageSec) + " > max_age_sec=" + maxAgeSec + ")");
    }
    repoFallbackUsed = 1;
  }

  const aiPath = path.join(inputReportsRoot, "ai_smoke_latest.json");
  const outJson = path.join(outputReportsRoot, "autodecision_latest.json");
  const outMd = path.join(outputReportsRoot, "autodecision_latest.md");

  if (!fs.existsSync(repoPathResolved)) throw new Error("BLOCK: missing " + repoPath + " and fallback " + repoPathResolved);
  const aiFallback = path.join(repoRoot, "docs/ops/reports/ai_smoke_latest.json");
  const aiPathResolved = fs.existsSync(aiPath) ? aiPath : aiFallback;
  if (evidenceRoot && !fs.existsSync(aiPath)) {
    throw new Error("BLOCK: AC25 input fallback disabled");
  }
  if (!fs.existsSync(aiPathResolved)) throw new Error("BLOCK: missing " + aiPath + " and fallback " + aiPathResolved);

  const repo = readJson(repoPathResolved);
  const ai = readJson(aiPathResolved);

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
      repo_contracts_fallback_used: repoFallbackUsed,
      repo_contracts_latest_json: "repo_contracts_latest.json",
      ai_smoke_latest_json: "ai_smoke_latest.json"
    }
  };

  if (evidenceRoot) {
    if (!fs.existsSync(outputReportsRoot)) {
      throw new Error("AUTODECISION_OUTPUT_ROOT_MISSING");
    }
  } else {
    fs.mkdirSync(outputReportsRoot, { recursive: true, mode: 0o700 });
  }
  const jsonBytes = Buffer.from(JSON.stringify(payload), "utf8");
  const markdownBytes = Buffer.from(
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
      "- repo_contracts_latest.json",
      "- ai_smoke_latest.json"
    ].join("\n"),
    "utf8",
  );
  writeAutodecisionOutputs({
    repoRoot,
    evidenceRoot,
    outJson,
    outMd,
    jsonBytes,
    markdownBytes,
  });
}

try {
  main();
  console.log("AUTODECISION_GENERATED=1");
  console.log("ERROR_CODE=NONE");
} catch (_error) {
  console.log("AUTODECISION_GENERATED=0");
  console.log("ERROR_CODE=AUTODECISION_GENERATION_FAILED");
  process.exitCode = 1;
}
