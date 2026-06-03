from __future__ import annotations

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

SOURCE_PATHS = [
    ROOT / "butler-desktop/src/lib/admin_policy/contracts.ts",
    ROOT / "butler-desktop/src/lib/admin_policy/client.ts",
    ROOT / "butler-desktop/src/components/v1_1/AdminPolicyConsole.tsx",
    ROOT / "butler-desktop/src/components/v1_1/CompanyFormatConsole.tsx",
]

def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    missing = [str(path) for path in SOURCE_PATHS if not path.exists()]
    if missing:
        print(json.dumps({"SELF_CHECK_PASS": False, "missing": missing}, ensure_ascii=False))
        return 1
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_PATHS)
    checks = {
        "allowed_endpoints_present": all(endpoint in combined for endpoint in [
            "/v1/admin/company-policy",
            "/v1/admin/company-format",
            "/v1/policy/evaluate",
            "/v1/admin/company-format/",
        ]),
        "forbidden_endpoint_zero": not re.search(r"/admin/company_policy|/admin/company_format|company-policy/active|company-format/list|rollback", combined),
        "browser_storage_zero": not re.search(r"localStorage|sessionStorage|indexedDB", combined),
        "nonlocal_network_zero": all("127.0.0.1:8765" in line for line in combined.splitlines() if "fetch(" in line),
        "box2_claim_zero": "박스 2 적용" not in combined or "별도 검증 전 표시하지 않습니다" in combined,
    }
    manifest = {str(path.relative_to(ROOT)): sha256_file(path) for path in SOURCE_PATHS}
    ok = all(checks.values())
    print(json.dumps({"SELF_CHECK_PASS": ok, "checks": checks, "sha256": manifest}, ensure_ascii=False, indent=2))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
