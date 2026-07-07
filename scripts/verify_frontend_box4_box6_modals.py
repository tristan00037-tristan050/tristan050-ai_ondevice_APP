#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

REQUIRED_FILES = [
    Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"),
    Path("butler-desktop/src/lib/cards/fileText.ts"),
    Path("butler-desktop/src/lib/box6/box6FormFillClient.ts"),
    Path("butler-desktop/src/lib/box4/box4ReviewClient.ts"),
    Path("butler-desktop/src/components/v1_1/ModalFrame.tsx"),
    Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"),
    Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"),
    Path("butler-desktop/src/__tests__/Box4Box6FrontendModals.test.tsx"),
]

STATIC_SCAN_FILES = [
    Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"),
    Path("butler-desktop/src/lib/cards/fileText.ts"),
    Path("butler-desktop/src/lib/box6/box6FormFillClient.ts"),
    Path("butler-desktop/src/lib/box4/box4ReviewClient.ts"),
    Path("butler-desktop/src/components/v1_1/ModalFrame.tsx"),
    Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"),
    Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"),
]


def fail(code: str) -> None:
    print("FRONTEND_BOX4_BOX6_MODALS_OK=0")
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


def main() -> int:
    legacy_source_key = "_".join(("source", "excerpt"))

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            fail("REQUIRED_FRONTEND_FILE_MISSING")

    app = read(Path("butler-desktop/src/App.tsx"))
    box6_client = read(Path("butler-desktop/src/lib/box6/box6FormFillClient.ts"))
    box4_client = read(Path("butler-desktop/src/lib/box4/box4ReviewClient.ts"))
    file_text = read(Path("butler-desktop/src/lib/cards/fileText.ts"))
    parser = read(Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"))
    modal_frame = read(Path("butler-desktop/src/components/v1_1/ModalFrame.tsx"))
    form_modal = read(Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"))
    review_modal = read(Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"))
    tests = read(Path("butler-desktop/src/__tests__/Box4Box6FrontendModals.test.tsx"))

    require_contains(
        app,
        [
            "import { FormFillModal }",
            "import { DocumentReviewModal }",
            "formFillModalOpen",
            "documentReviewModalOpen",
            "closeAllCardModals",
            "m === 'form_fill'",
            "m === 'document_review'",
            "<FormFillModal",
            "<DocumentReviewModal",
        ],
        "APP_WIRING_MISSING",
    )

    require_contains(
        box6_client,
        [
            "sidecarFetch('/api/analyze/stream'",
            "formData.append('card_mode', '6')",
            "formData.append(`file_${index}`, item.file)",
            "formData.append('file_count'",
            "parseAnalyzeStreamResult",
            "source_ref",
            "reason_code: string",
            "review_required: string[]",
            "LEGACY_SOURCE_KEY",
            "BOX6_LEGACY_MAPPING_SCHEMA",
            "RESULT_KEYS",
            "MAPPING_KEYS",
            "hasExactKeys",
            "UNFILLED_VALUES",
            "enforceBox6SecretGuard",
            "hasBox6SecretAutofill",
            "renderedStrings(result)",
            "보안 항목 자동기입이 감지되어 결과를 표시하지 않았습니다.",
        ],
        "BOX6_CLIENT_CONTRACT_MISSING",
    )
    mapping_start = box6_client.find("export type Box6FieldMapping = {")
    mapping_end = box6_client.find("};", mapping_start)
    if mapping_start < 0 or mapping_end < 0:
        fail("BOX6_MAPPING_TYPE_MISSING")
    mapping_segment = box6_client[mapping_start:mapping_end]
    if "review_required" in mapping_segment:
        fail("BOX6_MAPPING_LEVEL_REVIEW_FORBIDDEN")
    if legacy_source_key in box6_client:
        fail("BOX6_LEGACY_SOURCE_KEY_LITERAL_FORBIDDEN")

    require_contains(
        box4_client,
        [
            "sidecarFetch('/api/analyze/stream'",
            "formData.append('card_mode', '4')",
            "formData.append(`file_${index}`, item.file)",
            "formData.append('file_count'",
            "parseAnalyzeStreamResult",
            "hasBox4SecretLeak",
            "hasOnlyAllowedKeys",
            "renderedStrings(result)",
            "민감정보가 포함되어 결과를 표시하지 않았습니다.",
        ],
        "BOX4_CLIENT_CONTRACT_MISSING",
    )

    require_contains(
        file_text,
        [
            "MAX_FILES = 5",
            "MAX_CHARS_PER_FILE = 20000",
            "MAX_TOTAL_CHARS = 60000",
            "MAX_BYTES_PER_CHAR = 4",
            "ALLOWED_TEXT_EXT",
            "slice(0, byteLimit)",
        ],
        "FILE_LIMIT_CONTRACT_MISSING",
    )
    require_contains(
        parser,
        ["result_text", "result", "```", "결과 형식을 확인하지 못했습니다."],
        "PARSER_FAIL_SAFE_CONTRACT_MISSING",
    )
    require_contains(
        modal_frame + box6_client + box4_client + form_modal + review_modal,
        [
            'role="dialog"',
            'aria-modal="true"',
            "Escape",
            "previous?.focus()",
            "setAttribute('inert'",
            "event.key !== 'Tab'",
            "uiSafeSidecarErrorMessage",
            "safeExcerpt",
        ],
        "MODAL_ACCESSIBILITY_OR_REDACTION_MISSING",
    )
    require_contains(
        form_modal,
        [
            "mapping.source_ref || mapping.reason_code",
            "result.review_required.includes(mapping.target_label)",
            "result.unfilled_fields.includes(mapping.target_label)",
        ],
        "BOX6_MODAL_SCHEMA_RENDERING_MISSING",
    )
    if legacy_source_key in form_modal or "mapping.review_required" in form_modal:
        fail("BOX6_MODAL_LEGACY_SCHEMA_FORBIDDEN")

    require_contains(
        tests,
        [
            "card_mode')).toBe('6')",
            "body.get('file_0')",
            "body.get('files')).toBeNull()",
            "card_mode') === '4'",
            "unsupported_type",
            "too_many",
            "sk-test-secret-value-123456",
            "MAX_BYTES_PER_CHAR",
            "source_ref",
            "legacySourceKey",
            "[legacySourceKey]",
            "BOX6_LEGACY_MAPPING_SCHEMA",
            "review_required: ['API key']",
            "booleanReview",
            "raw_secret",
            "unsafeBox6FilledFormOnlyPayload",
            "source_ref: 'api key: sk-test-secret-value-123456'",
            "reason_code: 'FORBIDDEN_SECRET_FIELD sk-test-secret-value-123456'",
            "unfilled_fields: ['API key: sk-test-secret-value-123456']",
            "unsafeBox4SummarySecretPayload",
            "hasBox6SecretAutofill",
            "hasBox4SecretLeak",
            "민감정보가 포함되어 결과를 표시하지 않았습니다.",
            "document.querySelector('[inert]')",
            "shiftKey: true",
            "toHaveLength(0)",
        ],
        "REGRESSION_TEST_CONTRACT_MISSING",
    )
    if legacy_source_key in tests:
        fail("BOX6_TEST_LEGACY_SOURCE_KEY_LITERAL_FORBIDDEN")

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

    print("FRONTEND_BOX4_BOX6_MODALS_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
