#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

APP_PATH = Path("butler-desktop/src/App.tsx")
BOX6_CLIENT_PATH = Path("butler-desktop/src/lib/box6/box6FormFillClient.ts")
BOX4_CLIENT_PATH = Path("butler-desktop/src/lib/box4/box4ReviewClient.ts")
SECRET_PATTERNS_PATH = Path("butler-desktop/src/lib/cards/secretPatterns.ts")
TEST_PATH = Path("butler-desktop/src/__tests__/Box4Box6FrontendModals.test.tsx")
FIXTURE_PATH = Path("butler-desktop/src/__tests__/fixtures/secretFixtures.ts")

FORBIDDEN_DIFF_PATHS = [
    Path("butler_pc_core"),
    Path("butler_sidecar.py"),
    APP_PATH,
    Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"),
    Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"),
    Path("butler_pc_core/prompts/cards/card_04_document_review.yaml"),
    Path("butler_pc_core/prompts/cards/card_06_fill_external_form.yaml"),
    Path("scripts/verify_box4_document_review_activation.py"),
    Path("scripts/verify_box6_form_fill_activation.py"),
]

STATIC_SCAN_FILES = [
    SECRET_PATTERNS_PATH,
    BOX6_CLIENT_PATH,
    BOX4_CLIENT_PATH,
    Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"),
    Path("butler-desktop/src/lib/cards/fileText.ts"),
    Path("butler-desktop/src/components/v1_1/ModalFrame.tsx"),
    Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"),
    Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"),
]

EXPECTED_POSITIVE_COUNT = 16
EXPECTED_NEGATIVE_COUNT = 8


def fail(code: str) -> None:
    print("FRONTEND_BOX4_BOX6_MODAL_VERIFY_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def read(rel: Path) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        fail("SOURCE_FILE_MISSING")


def require_contains(source: str, needles: list[str], code: str) -> None:
    for needle in needles:
        if needle not in source:
            fail(code)


def extract_string_array(source: str, name: str) -> list[str]:
    match = re.search(rf"export const {name}\s*=\s*\[(.*?)\]\s+as const;", source, re.S)
    if not match:
        fail("FIXTURE_ARRAY_MISSING")
    return re.findall(r"'([^']*)'", match.group(1))


def extract_secret_pattern_source(source: str) -> str:
    delim_match = re.search(r"const SECRET_DELIM = String\.raw`([^`]+)`;", source)
    if not delim_match:
        fail("SECRET_DELIM_MISSING")
    secret_delim = delim_match.group(1)
    array_match = re.search(r"export const SECRET_PATTERN_SOURCE = \[(.*?)\]\.join\('\|'\);", source, re.S)
    if not array_match:
        fail("SECRET_PATTERN_SOURCE_MISSING")
    parts = []
    for part in re.findall(r"String\.raw`([^`]+)`", array_match.group(1)):
        parts.append(part.replace("${SECRET_DELIM}", secret_delim))
    if len(parts) < 8:
        fail("SECRET_PATTERN_SOURCE_INCOMPLETE")
    return "|".join(parts)


def count_definitions(needle: str, files: list[Path]) -> int:
    return sum(read(rel).count(needle) for rel in files if (ROOT / rel).exists())


def path_changed_against_head(rel: Path) -> bool:
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        return False
    try:
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^..HEAD", "--", str(rel)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def main() -> int:
    legacy_source_key = "_".join(("source", "excerpt"))

    for rel in [APP_PATH, BOX6_CLIENT_PATH, BOX4_CLIENT_PATH, SECRET_PATTERNS_PATH, TEST_PATH, FIXTURE_PATH]:
        if not (ROOT / rel).is_file():
            fail("REQUIRED_FRONTEND_FILE_MISSING")

    app = read(APP_PATH)
    box6_client = read(BOX6_CLIENT_PATH)
    box4_client = read(BOX4_CLIENT_PATH)
    secret_patterns = read(SECRET_PATTERNS_PATH)
    tests = read(TEST_PATH)
    fixtures = read(FIXTURE_PATH)

    require_contains(
        app,
        [
            "import { FormFillModal }",
            "import { DocumentReviewModal }",
            "m === 'form_fill'",
            "m === 'document_review'",
            "<FormFillModal",
            "<DocumentReviewModal",
        ],
        "APP_WIRING_MISSING",
    )

    require_contains(
        secret_patterns,
        [
            "export const SECRET_PATTERN_SOURCE",
            "export const SECRET_TEXT_RE = new RegExp(SECRET_PATTERN_SOURCE, 'i')",
            "value.length > 100_000",
            "SensitiveOutputBlockedError",
            "SENSITIVE_OUTPUT_BLOCKED:${fieldPath}",
        ],
        "SECRET_PATTERN_MODULE_MISSING",
    )
    if "new RegExp(SECRET_PATTERN_SOURCE, 'gi')" in secret_patterns or "/g" in secret_patterns:
        fail("SECRET_PATTERN_GLOBAL_FLAG_FORBIDDEN")

    if count_definitions("export const SECRET_PATTERN_SOURCE", [SECRET_PATTERNS_PATH, BOX6_CLIENT_PATH, BOX4_CLIENT_PATH]) != 1:
        fail("SECRET_PATTERN_SOURCE_NOT_SHARED")

    require_contains(
        box6_client,
        [
            "import { SECRET_PATTERN_SOURCE, containsSecretLikeText } from '../cards/secretPatterns'",
            "const SECRET_VALUE_RE = new RegExp(SECRET_PATTERN_SOURCE, 'i')",
            "renderedStrings(result)",
            "hasBox6SecretAutofill",
            "보안 항목 자동기입이 감지되어 결과를 표시하지 않았습니다.",
        ],
        "BOX6_SHARED_SECRET_PATTERN_MISSING",
    )
    if re.search(r"const SECRET_VALUE_RE\s*=\s*/", box6_client):
        fail("BOX6_LEGACY_DIRECT_SECRET_REGEX")

    require_contains(
        box4_client,
        [
            "import { SECRET_PATTERN_SOURCE, containsSecretLikeText } from '../cards/secretPatterns'",
            "const SECRET_TEXT_RE = new RegExp(SECRET_PATTERN_SOURCE, 'i')",
            "renderedStrings(result)",
            "hasBox4SecretLeak",
            "민감정보가 포함되어 결과를 표시하지 않았습니다.",
        ],
        "BOX4_SHARED_SECRET_PATTERN_MISSING",
    )
    if re.search(r"const SECRET_TEXT_RE\s*=\s*/", box4_client):
        fail("BOX4_LEGACY_DIRECT_SECRET_REGEX")

    require_contains(
        tests + fixtures,
        [
            "SECRET_POSITIVE_FIXTURES",
            "SECRET_NEGATIVE_FIXTURES",
            "containsSecretLikeText",
            "SECRET_TEXT_RE.global",
            "blocks shared positive fixtures across Box6 rendered output paths",
            "blocks shared positive fixtures across Box4 rendered output paths",
            "allows Box6 secret target labels when they are unfilled and listed for review",
            "blocks Box6 secret target labels when a value is autofilled",
        ],
        "SECRET_MATRIX_TESTS_MISSING",
    )

    if legacy_source_key in box6_client or legacy_source_key in tests:
        fail("LEGACY_SOURCE_EXCERPT_REINTRODUCED")
    mapping_start = box6_client.find("export type Box6FieldMapping = {")
    mapping_end = box6_client.find("};", mapping_start)
    if mapping_start < 0 or mapping_end < 0:
        fail("BOX6_MAPPING_TYPE_MISSING")
    if "review_required" in box6_client[mapping_start:mapping_end]:
        fail("LEGACY_MAPPING_REVIEW_REQUIRED_REINTRODUCED")

    pattern_source = extract_secret_pattern_source(secret_patterns)
    try:
        compiled = re.compile(pattern_source, re.I)
    except re.error:
        fail("SECRET_PATTERN_COMPILE_FAILED")
    positives = extract_string_array(fixtures, "SECRET_POSITIVE_FIXTURES")
    negatives = extract_string_array(fixtures, "SECRET_NEGATIVE_FIXTURES")
    if len(positives) != EXPECTED_POSITIVE_COUNT or len(negatives) != EXPECTED_NEGATIVE_COUNT:
        fail("SECRET_FIXTURE_COUNT_MISMATCH")

    positive_blocked = sum(1 for fixture in positives if compiled.search(fixture))
    negative_allowed = sum(1 for fixture in negatives if not compiled.search(fixture))
    if positive_blocked != EXPECTED_POSITIVE_COUNT:
        fail("SECRET_POSITIVE_MATRIX_FAILED")
    if negative_allowed != EXPECTED_NEGATIVE_COUNT:
        fail("SECRET_NEGATIVE_MATRIX_FAILED")

    for rel in STATIC_SCAN_FILES:
        source = read(rel)
        if legacy_source_key in source:
            fail("BOX6_LEGACY_SOURCE_KEY_LITERAL_FORBIDDEN")
        if "dangerouslySetInnerHTML" in source:
            fail("DANGEROUS_HTML_FORBIDDEN")
        if "localStorage" in source or "getSidecarCapabilityToken" in source:
            fail("MANUAL_TOKEN_ACCESS_FORBIDDEN")
        if "Authorization" in source:
            fail("MANUAL_AUTH_HEADER_FORBIDDEN")
        if "fetch(" in source and "sidecarFetch(" not in source:
            fail("DIRECT_FETCH_FORBIDDEN")

    raw_secret_echo = 0
    for source in [secret_patterns, box6_client, box4_client]:
        if "match[0]" in source or "matched" in source.lower() or "sk-test-secret-value" in source:
            raw_secret_echo = 1
    if raw_secret_echo:
        fail("RAW_SECRET_ECHO_DETECTED")

    for rel in FORBIDDEN_DIFF_PATHS:
        if path_changed_against_head(rel):
            fail("FORBIDDEN_LATEST_DIFF_PATH")

    print("FRONTEND_BOX4_BOX6_MODAL_VERIFY_OK=1")
    print("SECRET_PATTERN_SHARED=1")
    print(f"BOX6_SECRET_MATRIX_POSITIVE_BLOCKED={positive_blocked}/{EXPECTED_POSITIVE_COUNT}")
    print(f"BOX6_SECRET_MATRIX_NEGATIVE_ALLOWED={negative_allowed}/{EXPECTED_NEGATIVE_COUNT}")
    print(f"BOX4_SECRET_MATRIX_POSITIVE_BLOCKED={positive_blocked}/{EXPECTED_POSITIVE_COUNT}")
    print(f"BOX4_SECRET_MATRIX_NEGATIVE_ALLOWED={negative_allowed}/{EXPECTED_NEGATIVE_COUNT}")
    print("LEGACY_SOURCE_EXCERPT=0")
    print("LEGACY_MAPPING_REVIEW_REQUIRED=0")
    print("RAW_SECRET_ECHO=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
