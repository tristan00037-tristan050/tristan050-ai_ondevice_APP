#!/usr/bin/env bash
# 정책·양식 UI follow-up v1.2 verify — MAINDEV 8 ZERO + CODEX claim 3 (token_as_admin ·
# raw_template · forbidden_claim) 통합. AGENTS.md 의무 정합 (key=0/1 + short ERROR_CODE).
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

python3 - <<'PY'
import re
import subprocess
from pathlib import Path

ROOT = Path('.').resolve()

UI_SCAN_DIRS = [
    ROOT / "butler-desktop/src/components/v1_1/AdminPolicyConsole.tsx",
    ROOT / "butler-desktop/src/components/v1_1/CompanyFormatConsole.tsx",
    ROOT / "butler-desktop/src/lib/admin_policy",
    ROOT / "butler-desktop/src/__tests__/AdminPolicyConsole.test.tsx",
    ROOT / "butler-desktop/src/__tests__/CompanyFormatConsole.test.tsx",
]
TEST_PATH = ROOT / "tests/admin_policy/test_policy_format_registration_company_policy_api.py"

# verifier-self-exclude — 본 verify · scan · UI test 자체는 needle 리터럴 보유 (부재
# 검증 목적). 본문에 등장하더라도 self-검사 fail 회피.
SELF_EXCLUDED = {
    (ROOT / "scripts/verify_admin_policy_ui_followup_v1_2.sh").resolve(),
    (ROOT / "scripts/verify_admin_policy_format_v1_2.sh").resolve(),
    (ROOT / "scripts/run_security_scan_v1_2.py").resolve(),
    (ROOT / "scripts/run_admin_policy_ui_followup_self_check.py").resolve(),
    (ROOT / "butler-desktop/src/__tests__/AdminPolicyConsole.test.tsx").resolve(),
    (ROOT / "butler-desktop/src/__tests__/CompanyFormatConsole.test.tsx").resolve(),
}


def ui_files():
    for base in UI_SCAN_DIRS:
        if not base.exists():
            continue
        if base.is_file():
            if base.resolve() in SELF_EXCLUDED:
                continue
            yield base
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or "node_modules" in path.parts:
                continue
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            if path.resolve() in SELF_EXCLUDED:
                continue
            yield path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


errors: list[str] = []

# ① CONNECT_LOOP_CONTRACT_MODIFIED — git diff 가 schemas/connect_loop · docs/ssot 변경 포함 시 위반.
try:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout
except Exception:
    diff = ""
for path in diff.splitlines():
    if path.startswith("schemas/connect_loop/") or path.startswith("docs/ssot/connect_loop/"):
        errors.append("BLOCK_CONNECT_LOOP_CONTRACT")
        break

# 본 verify 의 모든 needle 검사는 UI scope (butler-desktop/src/components/v1_1/Admin*,
# CompanyFormat*, butler-desktop/src/lib/admin_policy) 한정.
for path in ui_files():
    text = read(path)
    # ② BROWSER_PERSISTENT_STORAGE
    if re.search(r"localStorage|sessionStorage|indexedDB", text):
        errors.append("BLOCK_BROWSER_PERSISTENT_STORAGE")
    # ③ NON_LOCAL_NETWORK: fetch/axios/WebSocket/sendBeacon 호출 중 127.0.0.1:8765 아닌 것
    for match in re.finditer(r"fetch\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket", text):
        line = text[:match.start()].count("\n") + 1
        line_text = text.splitlines()[line - 1] if 1 <= line <= len(text.splitlines()) else ""
        if "127.0.0.1:8765" not in line_text and "SIDECAR_BASE" not in line_text:
            errors.append("BLOCK_NON_LOCAL_NETWORK")
            break
    # ④ TOKEN_STORAGE_LOG_DOM
    if re.search(r"console\.(log|info|warn|error).*token|Authorization.*DOM|token.*DOM", text, re.I):
        errors.append("BLOCK_TOKEN_STORAGE_LOG_DOM")
    # ⑤ FORBIDDEN_ENDPOINT
    if re.search(r"/admin/company_policy|/admin/company_format|company-policy/active|company-format/list|rollback", text):
        errors.append("BLOCK_FORBIDDEN_ENDPOINT")
    # ⑥ BACKEND_GAP_CLAIM — UI가 backend 미존재 동작을 주장하면 위반.
    if re.search(r"external_send_rules.*body|external_send_rules.*JSON\.stringify|box2.*format_applied|UI.*encrypt", text):
        errors.append("BLOCK_BACKEND_GAP_CLAIM")
    # ⑦ SECRET_PATH_PII
    if re.search(r"sk-proj-|/Users/|/home/|/Volumes/|secret|password", text):
        errors.append("BLOCK_SECRET_PATH_PII")
    # CODEX 통합 ① TOKEN_AS_ADMIN — UI 가 capability token 을 admin role 로 캐스팅 / token 으로
    # admin 권한 추론하면 위반. admin RBAC 는 별도 헤더 (X-Admin-*).
    if re.search(r"token.*as\s+admin|admin\s*=.*token|role.*=.*token", text, re.I):
        errors.append("BLOCK_TOKEN_AS_ADMIN")
    # CODEX 통합 ② RAW_TEMPLATE — UI 가 template plaintext 를 노출/저장/로그 시 위반.
    # 정합 노출 = template_digest / template_ref(local-vault://) 만.
    if re.search(r"template_runtime_text\s*[:=].*input|console\..*template_runtime|alert\(.*template_runtime", text):
        errors.append("BLOCK_RAW_TEMPLATE")
    # CODEX 통합 ③ FORBIDDEN_CLAIM — UI 가 backend 가 보장하지 않은 본질을 자랑하면 위반.
    if re.search(r"회사 스타일을 학습했습니다|전사 양식 자동|박스 2.*적용 완료|production|release|APPROVED_FOR_PRODUCTION", text):
        errors.append("BLOCK_FORBIDDEN_CLAIM")

# ⑧ BINARY_ARTIFACT — staged binary 자산 0 (전 repo 가 아니라 PR scope 한정).
staged = subprocess.run(
    ["git", "diff", "--cached", "--name-only"],
    capture_output=True, text=True, check=False,
).stdout
for path in staged.splitlines():
    if any(path.endswith(suf) for suf in [".safetensors", ".gguf", ".bin", ".npy", ".pkl"]):
        errors.append("BLOCK_BINARY_ARTIFACT")
        break

# CLAUDE_FOOTER — 본 PR scope 한정.
for path in ui_files():
    text = read(path)
    if "Generated with " + "Claude Code" in text or "Co-Authored-By: " + "Claude" in text:
        errors.append("BLOCK_CLAUDE_FOOTER")
        break
if TEST_PATH.exists():
    text = read(TEST_PATH)
    if "Generated with " + "Claude Code" in text or "Co-Authored-By: " + "Claude" in text:
        errors.append("BLOCK_CLAUDE_FOOTER")

CHECK_ORDER = [
    ("CONNECT_LOOP_CONTRACT_MODIFIED_ZERO", "BLOCK_CONNECT_LOOP_CONTRACT"),
    ("BROWSER_PERSISTENT_STORAGE_ZERO", "BLOCK_BROWSER_PERSISTENT_STORAGE"),
    ("NON_LOCAL_NETWORK_ZERO", "BLOCK_NON_LOCAL_NETWORK"),
    ("TOKEN_STORAGE_LOG_DOM_ZERO", "BLOCK_TOKEN_STORAGE_LOG_DOM"),
    ("FORBIDDEN_ENDPOINT_ZERO", "BLOCK_FORBIDDEN_ENDPOINT"),
    ("BACKEND_GAP_CLAIM_ZERO", "BLOCK_BACKEND_GAP_CLAIM"),
    ("SECRET_PATH_PII_ZERO", "BLOCK_SECRET_PATH_PII"),
    ("BINARY_ARTIFACT_ZERO", "BLOCK_BINARY_ARTIFACT"),
    ("TOKEN_AS_ADMIN_ZERO", "BLOCK_TOKEN_AS_ADMIN"),
    ("RAW_TEMPLATE_ZERO", "BLOCK_RAW_TEMPLATE"),
    ("FORBIDDEN_CLAIM_ZERO", "BLOCK_FORBIDDEN_CLAIM"),
    ("CLAUDE_FOOTER_ZERO", "BLOCK_CLAUDE_FOOTER"),
]

# AGENTS.md 의무: key=0/1 + short ERROR_CODE 만. PASS=1, FAIL=0.
err_set = set(errors)
for key, code in CHECK_ORDER:
    print(f"{key}={0 if code in err_set else 1}")

if err_set:
    for code in sorted(err_set):
        print(code)
    raise SystemExit(1)
PY
