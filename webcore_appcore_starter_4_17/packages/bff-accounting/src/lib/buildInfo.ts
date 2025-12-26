/**
 * ✅ P0: BuildInfo 부트 시 1회 로드 + 메모리 캐시
 * 목적: /healthz 요청마다 디스크 I/O를 하지 않음 (운영 성능 안전)
 * 원칙: 파싱/검증 실패 시 즉시 프로세스 종료(exit 1)
 */

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export type BuildInfo = {
  buildSha: string; // 40-hex
  buildShaShort: string; // 7-hex
  buildTime: string; // ISO8601
};

let CACHED: BuildInfo | null = null;

function assertHex(s: string, n: number, name: string): void {
  const re = n === 40 ? /^[0-9a-f]{40}$/i : /^[0-9a-f]{7}$/i;
  if (!re.test(s)) {
    throw new Error(`invalid ${name} (expected ${n}-hex): "${s}"`);
  }
}

/**
 * BuildInfo를 부트 시 1회 로드하고 캐시합니다.
 * 실패 시 예외를 던지므로, 호출자는 try-catch로 처리하고 exit(1) 해야 합니다.
 */
export function getBuildInfoOrThrow(): BuildInfo {
  if (CACHED) {
    return CACHED;
  }

  // dist 기준 단일 신뢰원천: build_info.json
  // ESM에서 안전하게 경로 산출 (import.meta.url → __dirname)
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  // src/lib/buildInfo.ts → dist/lib/buildInfo.js → dist/build_info.json
  const buildInfoPath = join(__dirname, "..", "build_info.json");

  if (!existsSync(buildInfoPath)) {
    throw new Error(`build_info.json not found: ${buildInfoPath}`);
  }

  const raw = readFileSync(buildInfoPath, "utf-8");
  let j: any;
  try {
    j = JSON.parse(raw);
  } catch (error: any) {
    throw new Error(`build_info.json parse failed: ${error.message}`);
  }

  const buildSha = String(j?.buildSha ?? "").trim();
  const buildShaShort = String(j?.buildShaShort ?? "").trim();
  const buildTime = String(j?.buildTime ?? "").trim();

  // FAIL-CLOSED: unknown/빈값/형식불일치 즉시 예외
  if (!buildSha || buildSha === "unknown") {
    throw new Error(`buildSha is missing or unknown: "${buildSha}"`);
  }
  assertHex(buildSha, 40, "buildSha");

  if (!buildShaShort || buildShaShort === "unknown") {
    throw new Error(`buildShaShort is missing or unknown: "${buildShaShort}"`);
  }
  assertHex(buildShaShort, 7, "buildShaShort");

  if (!buildTime || buildTime.toLowerCase() === "unknown") {
    throw new Error(`invalid buildTime: "${buildTime}"`);
  }

  // ISO8601 형식 간단 체크
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(buildTime)) {
    throw new Error(`buildTime format invalid (expected ISO8601): "${buildTime}"`);
  }

  CACHED = { buildSha, buildShaShort, buildTime };
  return CACHED;
}

