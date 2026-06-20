#!/usr/bin/env python3
"""Static raw-zero verifier for the B (supersede + known-bad) implementation files.

Scans only the B implementation/test files in this repo and asserts:
  - no absolute home paths, emails, or api-key/bearer tokens leak into source,
  - no new status enum value is introduced (status stays CANDIDATE/ACTIVE/DEPRECATED),
  - no semantic-equivalence overclaim ("same meaning" / 의미 동등) — matcher is keyword/pattern only,
  - the company_fact status enum (STATUS_VALUES) is still the sealed 3-value set.

Exit 0 and print *_=1 lines on success; exit 1 and print *=0 lines on any violation.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    "butler_pc_core/company_fact/known_bad.py",
    "butler_pc_core/company_fact/storage.py",
    "butler_pc_core/company_fact/routes.py",
    "butler-desktop/src/lib/company_fact/contracts.ts",
    "butler-desktop/src/lib/company_fact/client.ts",
    "butler-desktop/src/components/v1_1/CompanyFactApprovalConsole.tsx",
    "tests/company_fact/test_b_supersede_known_bad.py",
    "butler-desktop/src/__tests__/companyFactClient.test.ts",
    "butler-desktop/src/__tests__/CompanyFactApprovalConsole.test.tsx",
]

FORBIDDEN_RAW_PATTERNS = [
    re.compile("/" + "Us" + "ers" + r"/[^\s\"']+"),  # absolute macOS home paths
    re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email
    re.compile(r"(?i)(sk-[A-Za-z0-9_-]{10,}|api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._~+/=-]{10,})"),
]
# B must not add a new status enum value. These quoted tokens must not appear as status strings.
FORBIDDEN_STATUS_ENUM = ['"REJECTED"', "'REJECTED'", '"KNOWN_BAD_SUSPECTED"', "'KNOWN_BAD_SUSPECTED'"]
FORBIDDEN_CLAIMS = [
    "semantic guarantee",
    "meaning-equivalent",
    "all same meaning",
    "same meaning",
    "의미 동등",
    "같은 뜻",
]

errors: set[str] = set()

for rel in TARGETS:
    path = ROOT / rel
    if not path.is_file():
        errors.add("TARGET_MISSING")
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    for pattern in FORBIDDEN_RAW_PATTERNS:
        if pattern.search(text):
            errors.add("RAW_PATTERN_PRESENT")
            break
    for token in FORBIDDEN_STATUS_ENUM:
        if token in text:
            errors.add("FORBIDDEN_STATUS_ENUM_PRESENT")
            break
    for claim in FORBIDDEN_CLAIMS:
        if claim in text:
            errors.add("FORBIDDEN_SEMANTIC_CLAIM_PRESENT")
            break

# Positive assertion: status enum is still the sealed 3-value set.
# Static-only: do not import butler_pc_core here because repo guards may run
# without serving dependencies installed.
contracts_path = ROOT / "butler_pc_core/company_fact/contracts.py"
contracts_text = contracts_path.read_text(encoding="utf-8", errors="ignore")
status_match = re.search(r"STATUS_VALUES\s*=\s*\{(?P<body>[^}]+)\}", contracts_text, flags=re.MULTILINE)
if not status_match:
    errors.add("STATUS_ENUM_NOT_FOUND")
else:
    values = set(re.findall(r"['\"]([A-Z_]+)['\"]", status_match.group("body")))
    if values != {"CANDIDATE", "ACTIVE", "DEPRECATED"}:
        errors.add("STATUS_ENUM_EXTENDED")

if errors:
    for code in sorted(errors):
        print(f"{code}=0")
    raise SystemExit(1)

print("RAW_ZERO_REPO_VERIFY=1")
print("FORBIDDEN_STATUS_ENUM_ZERO=1")
print("SEMANTIC_OVERCLAIM_ZERO=1")
print("STATUS_ENUM_SEALED=1")
