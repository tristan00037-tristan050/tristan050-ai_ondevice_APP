import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

// TS 유틸을 런타임에서 쓰기 위해 간단한 로컬 구현을 사용
// (여기서는 strict X.Y.Z만 허용)
function parseSemverStrict(s) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(s).trim());
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]) };
}

function compareSemver(a, b) {
  const pa = parseSemverStrict(a);
  const pb = parseSemverStrict(b);
  if (!pa || !pb) return null;
  if (pa.major !== pb.major) return pa.major < pb.major ? -1 : 1;
  if (pa.minor !== pb.minor) return pa.minor < pb.minor ? -1 : 1;
  if (pa.patch !== pb.patch) return pa.patch < pb.patch ? -1 : 1;
  return 0;
}

function isNonEmptyString(x) {
  return typeof x === "string" && x.trim().length > 0;
}

export function checkCompatOrBlock({ compat, runtime_semver, gateway_semver }) {
  if (!compat) return { ok: false, reason_code: "MODEL_PACK_COMPAT_MISSING" };

  // 누락도 무조건 차단
  if (!isNonEmptyString(runtime_semver) || !isNonEmptyString(gateway_semver)) {
    return { ok: false, reason_code: "MODEL_PACK_COMPAT_SEMVER_INVALID" };
  }

  const cr = compareSemver(runtime_semver, compat.min_runtime_semver);
  const cg = compareSemver(gateway_semver, compat.min_gateway_semver);

  if (cr === null || cg === null) return { ok: false, reason_code: "MODEL_PACK_COMPAT_SEMVER_INVALID" };
  if (cr < 0) return { ok: false, reason_code: "MODEL_PACK_COMPAT_RUNTIME_TOO_LOW" };
  if (cg < 0) return { ok: false, reason_code: "MODEL_PACK_COMPAT_GATEWAY_TOO_LOW" };
  return { ok: true };
}

