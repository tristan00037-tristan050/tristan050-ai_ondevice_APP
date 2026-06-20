#!/usr/bin/env python3
"""Static raw-zero verifier for company_learning C implementation files.

This is a source scan only. It intentionally avoids importing sidecar or serving
modules so it can run in minimal CI environments.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BACKEND_TARGETS = [
    "butler_pc_core/company_learning/__init__.py",
    "butler_pc_core/company_learning/folder_ingest.py",
    "butler_pc_core/company_learning/job_store.py",
    "butler_pc_core/company_learning/understanding.py",
    "butler_pc_core/company_learning/handoff.py",
    "butler_pc_core/sidecar/routes/company_learning.py",
]

FRONTEND_TARGETS = [
    "butler-desktop/src/lib/company_learning/contracts.ts",
    "butler-desktop/src/lib/company_learning/client.ts",
    "butler-desktop/src/components/v1_1/CompanyLearningConsole.tsx",
]

errors: set[str] = set()

FORBIDDEN_BACKEND_SUBSTRINGS = [
    "source_kind",
    "file_name",
    "source_doc_name",
    "local_path",
    "snippet",
    "requests.",
    "httpx.",
    "urllib.request",
    "telemetry",
    "analytics",
]

FORBIDDEN_FRONTEND_SUBSTRINGS = [
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "console.log",
    "console.warn",
    "console.error",
    "source_kind",
    "source_doc_name",
    "local_path",
    "snippet",
    "모든 업무 완전 이해",
    "자동 학습 완료",
    "클라우드 색인",
]

RAW_VALUE_PATTERNS = [
    re.compile("/" + "Us" + "ers" + r"/[^\s\"'`]+"),
    re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._~+/=-]{10,}|sk-[A-Za-z0-9_-]{10,})"),
]


def read_target(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        errors.add(f"TARGET_MISSING:{rel}")
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


for rel in BACKEND_TARGETS:
    text = read_target(rel)
    for forbidden in FORBIDDEN_BACKEND_SUBSTRINGS:
        if forbidden in text:
            errors.add(f"BACKEND_FORBIDDEN:{forbidden}")
    for pattern in RAW_VALUE_PATTERNS:
        if pattern.search(text):
            errors.add("BACKEND_RAW_LITERAL_PRESENT")

for rel in FRONTEND_TARGETS:
    text = read_target(rel)
    for forbidden in FORBIDDEN_FRONTEND_SUBSTRINGS:
        if forbidden in text:
            errors.add(f"FRONTEND_FORBIDDEN:{forbidden}")
    for pattern in RAW_VALUE_PATTERNS:
        if pattern.search(text):
            errors.add("FRONTEND_RAW_LITERAL_PRESENT")

routes_text = read_target("butler_pc_core/sidecar/routes/company_learning.py")
for required in ("_TOKEN_MANAGER.verify_authorization_header", "verify_admin_context", "LOCALHOST_HOSTS", "_verify_localhost"):
    if required not in routes_text:
        errors.add(f"ROUTE_AUTH_PATTERN_MISSING:{required}")

ingest_text = read_target("butler_pc_core/company_learning/folder_ingest.py")
if ".rglob(" in ingest_text:
    errors.add("INGEST_RGLOBAL_TRAVERSAL_PRESENT")
for required in (
    "MAX_OOXML_MEMBERS",
    "MAX_OOXML_UNCOMPRESSED_BYTES",
    "MAX_OOXML_COMPRESSION_RATIO",
    "MAX_EXTRACTED_CHARS_PER_FILE",
    "MAX_TOTAL_EXTRACTED_CHARS",
    "MAX_PDF_PAGES",
    "_validate_signature",
    "_guard_ooxml_archive",
):
    if required not in ingest_text:
        errors.add(f"INGEST_BACKPORT_PATTERN_MISSING:{required}")

capability_text = read_target("butler-desktop/src-tauri/capabilities/default.json")
if '"dialog:allow-open"' not in capability_text:
    errors.add("TAURI_DIALOG_OPEN_PERMISSION_MISSING")

handoff_text = read_target("butler_pc_core/company_learning/handoff.py")
for required in ("schema_version\": \"learning_event.v1", "verified_for_training\": False", "target_box_id\": \"helper1"):
    if required not in handoff_text:
        errors.add(f"HANDOFF_SCHEMA_PATTERN_MISSING:{required}")

if errors:
    for code in sorted(errors):
        print(f"{code}=0")
    raise SystemExit(1)

print("C_RAW_ZERO_REPO_VERIFY=1")
print("C_EXTERNAL_SEND_ZERO=1")
print("C_BROWSER_PERSIST_ZERO=1")
print("C_SOURCE_KIND_ZERO=1")
print("C_EVIDENCE_SNIPPET_ZERO=1")
