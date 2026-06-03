"""CODEX 보안 5 ZERO scan — 본 PR 범위 정합 (박스 3 머지본 환경).

CODEX 원본은 connect_loop schemas·docs/ssot 미존재 격리 zip 환경에서 *부재 자체* 와
repo 전체 UI/evidence 스캔을 검사로 사용했다. 박스 3 머지본 repo 에서는 schemas/connect_loop,
docs/ssot, butler-desktop 가 기존 자산으로 존재하므로 본 PR 의 5 ZERO 의무를 *본 PR 범위
(PR_PATHS)* 한정으로 정합화한다 — 본 PR 이 들고 온 자산이 그 경로를 수정/포함하지 않음 +
raw/path/secret/token storage/network leak/training artifact 0 건 검증.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PR_PATHS = (
    "butler_pc_core/company_policy",
    "butler_pc_core/cards/box3/adapters/company_format_adapter.py",
    "butler_pc_core/sidecar/routes/admin_policy_format.py",
    "tests/company_policy",
    "tests/admin_policy",
    "scripts/run_admin_policy_format_self_check.py",
    "scripts/run_security_scan_v1_2.py",
    "scripts/verify_admin_policy_format_v1_2.sh",
)

# 검증 도구 자체(verifier-self-exclude) — needle 리터럴을 검증용으로 보유.
SELF_EXCLUDED = {
    (ROOT / "tests" / "admin_policy" / "test_security_5_zero.py").resolve(),
    (ROOT / "tests" / "admin_policy" / "test_policy_format_registration.py").resolve(),
    (ROOT / "scripts" / "run_security_scan_v1_2.py").resolve(),
    (ROOT / "scripts" / "verify_admin_policy_format_v1_2.sh").resolve(),
}

BINARY_SUFFIXES = {
    ".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm", ".pdf",
    ".zip", ".gz", ".tar", ".db", ".sqlite", ".so", ".dylib",
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def pr_files() -> list[Path]:
    files: list[Path] = []
    for rel in PR_PATHS:
        base = ROOT / rel
        if base.is_file():
            if base.resolve() in SELF_EXCLUDED:
                continue
            files.append(base)
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix in BINARY_SUFFIXES:
                continue
            if path.resolve() in SELF_EXCLUDED:
                continue
            files.append(path)
    return files


def grep_files(files: list[Path], pattern: str) -> list[str]:
    regex = re.compile(pattern)
    hits: list[str] = []
    for path in files:
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
    return hits


def non_local_network_hits(files: list[Path]) -> list[str]:
    url_re = re.compile(r"https?://[^\"'\s)]+")
    hits: list[str] = []
    for path in files:
        if path.suffix not in {".tsx", ".ts", ".jsx", ".js", ".py"}:
            continue
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            for match in url_re.findall(line):
                if not match.startswith("http://127.0.0.1:8765"):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}:{match}")
    return hits


def main() -> int:
    files = pr_files()
    pr_text = "\n".join(read_text(p) for p in files)
    checks = {
        # 박스 3 머지본 환경: schemas/connect_loop · docs/ssot 는 기존 자산(존재). 본 PR 범위
        # 안에서 그 경로를 수정/import/포함하지 않음을 검증한다.
        "CONNECT_LOOP_CONTRACT_MODIFIED_ZERO": (
            "schemas/connect_loop" not in pr_text
            and "docs/ssot/connect_loop" not in pr_text
        ),
        "TOKEN_STORAGE_LOG_ZERO": not grep_files(
            files, r"localStorage|sessionStorage|indexedDB|console\.log"
        ),
        "NON_LOCAL_NETWORK_ZERO": not non_local_network_hits(files),
        # raw_text_logged / raw_doc_logged 는 audit metric flag (raw 0 검증용)이라 허용.
        # 정밀 매치: raw_text · raw_doc 단어 단독 사용만 차단(verify.sh 와 동일 의미).
        "RAW_SECRET_PATH_SCAN_ZERO": not grep_files(
            files,
            r"raw_text(?!_logged)|raw_doc(?!_logged)|sk-proj-|/Users/|/home/|/Volumes/",
        ),
        "TRAINING_MODEL_ARTIFACT_ZERO": not grep_files(
            files, r"\bTrainer\b|save_pretrained|safetensors|gguf"
        ),
    }
    payload = {
        "schema_version": "admin_policy_format.security_scan.v1_2",
        "checks": checks,
        "all_zero": all(checks.values()),
        "scope_note": (
            "본 PR 범위(PR_PATHS) 한정 5 ZERO 검증. verifier-self-exclude 적용. "
            "박스 3 머지본의 기존 자산(schemas/connect_loop, docs/ssot, butler-desktop 등)은 "
            "본 PR 패키지 외부 — 본 PR 이 그 경로를 수정/포함하지 않음을 텍스트 검사로 확인."
        ),
    }
    out = ROOT / "evidence" / "admin_policy_format" / "security_scan_v1_2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["all_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
