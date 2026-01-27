import fs from "node:fs";
import path from "node:path";
import { validateMetaOnlyWithSSOT, type MetaOnlySSOT } from "../../../shared/meta_only/validator_core";

function readSSOT(): MetaOnlySSOT {
  const p = path.join(process.cwd(), "docs/ops/contracts/META_ONLY_ALLOWLIST_SSOT.json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

export function validateMetaOnly(payload: any): { ok: true } | { ok: false; reason_code: string; detail: any } {
  const ssot = readSSOT();
  return validateMetaOnlyWithSSOT(payload, ssot);
}
