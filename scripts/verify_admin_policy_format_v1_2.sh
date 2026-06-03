#!/usr/bin/env bash
# MAINDEV verify_admin_policy_format_v1_2.sh — 본 PR 범위 정합 (박스 3 머지본 환경).
#
# MAINDEV 원본은 connect_loop schemas·docs/ssot 미존재 격리 zip 환경 가정으로 디렉터리
# *존재 자체*를 BLOCK 처리했고, 토큰/네트워크/raw 패턴을 repo 전체에서 검색했다. 박스 3
# 머지본 repo 는 두 디렉터리와 butler-desktop 등이 기존 자산으로 존재하므로 본 PR 의
# 검증을 *본 PR 범위(PR_PATHS)* 한정으로 정합화한다.
set -euo pipefail

ROOT="${1:-.}"

python3 - "$ROOT" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()

PR_PATHS = [
    "butler_pc_core/company_policy",
    "butler_pc_core/cards/box3/adapters/company_format_adapter.py",
    "butler_pc_core/sidecar/routes/admin_policy_format.py",
    "tests/company_policy",
    "tests/admin_policy",
    "scripts/run_admin_policy_format_self_check.py",
    "scripts/run_security_scan_v1_2.py",
    "scripts/verify_admin_policy_format_v1_2.sh",
]

SELF_EXCLUDED = {
    (root / "tests/admin_policy/test_security_5_zero.py").resolve(),
    (root / "tests/admin_policy/test_policy_format_registration.py").resolve(),
    (root / "scripts/run_security_scan_v1_2.py").resolve(),
    (root / "scripts/verify_admin_policy_format_v1_2.sh").resolve(),
}

BIN_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
                ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm", ".pdf",
                ".zip", ".gz", ".tar", ".db", ".sqlite", ".so", ".dylib"}


def files():
    for rel in PR_PATHS:
        base = root / rel
        if base.is_file():
            if base.resolve() in SELF_EXCLUDED:
                continue
            yield base
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix in BIN_SUFFIXES:
                continue
            if path.resolve() in SELF_EXCLUDED:
                continue
            yield path


CHECK_ORDER = [
    ("CONNECT_LOOP_CONTRACT_MODIFIED_ZERO", "BLOCK_CONNECT_LOOP_CONTRACT"),
    ("TOKEN_STORAGE_LOG_ZERO", "BLOCK_TOKEN_STORAGE_OR_LOG"),
    ("NON_LOCAL_NETWORK_ZERO", "BLOCK_NON_LOCAL_NETWORK"),
    ("RAW_SECRET_PATH_SCAN_ZERO", "BLOCK_RAW_SECRET_PATH"),
    ("TRAINING_MODEL_ARTIFACT_ZERO", "BLOCK_TRAINING_MODEL_ARTIFACT"),
    ("CLAUDE_FOOTER_ZERO", "BLOCK_CLAUDE_FOOTER"),
]
errors: set[str] = set()

token_patterns = [
    re.compile(r"localStorage.*token", re.I),
    re.compile(r"sessionStorage.*token", re.I),
    re.compile(r"indexedDB.*token", re.I),
    re.compile(r"console\.log\(.*token", re.I),
]
network_patterns = [re.compile(r"fetch\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket")]
raw_patterns = [
    re.compile(r"raw_text(?!_logged)", re.I),
    re.compile(r"sk-" + r"proj-", re.I),
    re.compile(r"/" + r"Users/"),
    re.compile(r"/" + r"home/"),
    re.compile(r"/" + r"Volumes/"),
    re.compile(r"BEGIN " + r"PRIVATE KEY"),
    re.compile(r"Authori" + r"zation: Bear" + r"er", re.I),
]

# 본 PR 범위 안에서 schemas/connect_loop · docs/ssot/connect_loop 경로를
# 수정/포함하지 않음을 텍스트로 검증한다.
pr_text_acc = []

for path in files():
    if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".md", ".json", ".txt"}:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    pr_text_acc.append(text)
    # AGENTS.md 의무(line 6): "verify 출력은 판정만 — 키=0/1 + 짧은 ERROR_CODE 만 허용".
    # 본 verify 가 path/pattern/line 디테일을 노출하지 않도록 짧은 ERROR_CODE 만 보유.
    for pattern in token_patterns:
        if pattern.search(text):
            errors.add("BLOCK_TOKEN_STORAGE_OR_LOG")
    for pattern in network_patterns:
        for match in pattern.finditer(text):
            line = text[:match.start()].count("\n") + 1
            line_text = text.splitlines()[line - 1] if 1 <= line <= len(text.splitlines()) else ""
            if "127.0.0.1:8765" not in line_text:
                errors.add("BLOCK_NON_LOCAL_NETWORK")
    for pattern in raw_patterns:
        if pattern.search(text):
            errors.add("BLOCK_RAW_SECRET_PATH")

joined = "\n".join(pr_text_acc)
if "schemas/connect_loop" in joined or "docs/ssot/connect_loop" in joined:
    errors.add("BLOCK_CONNECT_LOOP_CONTRACT")

for path in files():
    if path.suffix in {".safetensors", ".gguf", ".bin", ".npy", ".pkl"}:
        errors.add("BLOCK_TRAINING_MODEL_ARTIFACT")

bad_footer = ["Generated with " + "Claude Code", "Co-Authored-By: " + "Claude"]
for path in files():
    if path.suffix not in {".py", ".ts", ".tsx", ".md", ".sh", ".txt", ".json"}:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for needle in bad_footer:
        if needle in text:
            errors.add("BLOCK_CLAUDE_FOOTER")
            break

# AGENTS.md 의무: 각 key 는 *판정만* — PASS=1 / FAIL=0.
for key, code in CHECK_ORDER:
    print(f"{key}={0 if code in errors else 1}")

if errors:
    # 짧은 ERROR_CODE 만 노출 (중복 제거 + 정렬). path/pattern/line 노출 0.
    for code in sorted(errors):
        print(code)
    raise SystemExit(1)
PY
