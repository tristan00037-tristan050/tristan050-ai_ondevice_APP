// packages/common/src/reason_codes/reason_codes_v1_data.mjs
import fs from "node:fs";

function extractReasonCodesOrThrow(tsText) {
  const m = tsText.match(/export\s+const\s+REASON_CODES_V1\s*=\s*\[(.*?)\]\s*as\s+const\s*;/s);
  if (!m) throw new Error("REASON_CODES_V1_PARSE_FAIL");
  const body = m[1];
  const codes = [...body.matchAll(/"([^"]+)"/g)].map((x) => x[1]).filter(Boolean);
  if (codes.length === 0) throw new Error("REASON_CODES_V1_EMPTY");
  return codes;
}

const TS_PATH = new URL("./reason_codes_v1.ts", import.meta.url);
const TS_TEXT = fs.readFileSync(TS_PATH, "utf8");
export const REASON_CODES_V1 = extractReasonCodesOrThrow(TS_TEXT);
const SET = new Set(REASON_CODES_V1);

export function assertReasonCodeV1(x) {
  if (!SET.has(x)) throw new Error(`REASON_CODE_INVALID:${x}`);
  return x;
}

