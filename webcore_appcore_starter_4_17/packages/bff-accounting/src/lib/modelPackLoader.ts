/**
 * P2-AI-01: Model Pack Loader
 * 목적: model_id로 모델팩 로드 (로컬 파일만, code-only 에러)
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import crypto from "node:crypto";

// B-2) __dirname 설정 (ESM)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

type ModelPack = {
  pack_id: string;
  version: string;
  param: { salt: number };
  manifest_sha256: string;
};

function sha256Hex(buf: Buffer): string {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

export function loadModelPackOrThrow(modelId: string): ModelPack {
  if (!modelId || typeof modelId !== "string") {
    const err: any = new Error("PACK_ID_INVALID");
    err.code = "PACK_ID_INVALID";
    throw err;
  }

  // B-2) model_packs 경로를 process.cwd 의존에서 제거 (상향 탐색)
  // __dirname에서 시작해서 model_packs 디렉토리를 찾을 때까지 상위로 탐색
  let searchDir = __dirname;
  let repoRoot: string | null = null;
  const maxDepth = 10; // 무한 루프 방지
  
  for (let i = 0; i < maxDepth; i++) {
    const testPath = path.resolve(searchDir, "model_packs");
    if (fs.existsSync(testPath) && fs.statSync(testPath).isDirectory()) {
      repoRoot = searchDir;
      break;
    }
    const parent = path.resolve(searchDir, "..");
    if (parent === searchDir) {
      // 루트에 도달
      break;
    }
    searchDir = parent;
  }
  
  if (!repoRoot) {
    const err: any = new Error("PACK_ROOT_NOT_FOUND");
    err.code = "PACK_ROOT_NOT_FOUND";
    throw err;
  }
  
  const packPath = path.resolve(repoRoot, "model_packs", modelId, "pack.json");

  let raw: Buffer;
  try {
    raw = fs.readFileSync(packPath);
  } catch {
    const err: any = new Error("PACK_NOT_FOUND");
    err.code = "PACK_NOT_FOUND";
    throw err;
  }

  const manifest = sha256Hex(raw);

  let obj: any;
  try {
    obj = JSON.parse(raw.toString("utf8"));
  } catch {
    const err: any = new Error("PACK_JSON_INVALID");
    err.code = "PACK_JSON_INVALID";
    throw err;
  }

  // 최소 스키마 검증(값을 메시지에 포함하지 않음)
  if (!obj || typeof obj !== "object") {
    const err: any = new Error("PACK_SCHEMA_INVALID");
    err.code = "PACK_SCHEMA_INVALID";
    throw err;
  }
  if (typeof obj.pack_id !== "string" || typeof obj.version !== "string") {
    const err: any = new Error("PACK_SCHEMA_INVALID");
    err.code = "PACK_SCHEMA_INVALID";
    throw err;
  }
  const salt = obj?.param?.salt;
  if (typeof salt !== "number") {
    const err: any = new Error("PACK_PARAM_INVALID");
    err.code = "PACK_PARAM_INVALID";
    throw err;
  }

  return {
    pack_id: obj.pack_id,
    version: obj.version,
    param: { salt },
    manifest_sha256: manifest,
  };
}

