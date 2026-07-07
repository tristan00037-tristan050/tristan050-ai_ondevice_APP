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
    Path("butler-desktop/src/components/v1_1/FormFillModal.tsx"),
    Path("butler-desktop/src/components/v1_1/DocumentReviewModal.tsx"),
    Path("butler-desktop/src/__tests__/Box4Box6FrontendModals.test.tsx"),
]

STATIC_SCAN_FILES = [
    Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"),
    Path("butler-desktop/src/lib/cards/fileText.ts"),
    Path("butler-desktop/src/lib/box6/box6FormFillClient.ts"),
    Path("butler-desktop/src/lib/box4/box4ReviewClient.ts"),
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
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            fail("REQUIRED_FRONTEND_FILE_MISSING")

    app = read(Path("butler-desktop/src/App.tsx"))
    box6_client = read(Path("butler-desktop/src/lib/box6/box6FormFillClient.ts"))
    box4_client = read(Path("butler-desktop/src/lib/box4/box4ReviewClient.ts"))
    file_text = read(Path("butler-desktop/src/lib/cards/fileText.ts"))
    parser = read(Path("butler-desktop/src/lib/cards/analyzeStreamResult.ts"))
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
        ["sidecarFetch('/api/analyze/stream'", "formData.append('card_mode', '6')", "parseAnalyzeStreamResult"],
        "BOX6_CLIENT_CONTRACT_MISSING",
    )
    require_contains(
        box4_client,
        ["sidecarFetch('/api/analyze/stream'", "formData.append('card_mode', '4')", "parseAnalyzeStreamResult"],
        "BOX4_CLIENT_CONTRACT_MISSING",
    )

    require_contains(
        file_text,
        ["MAX_FILES = 5", "MAX_CHARS_PER_FILE = 20000", "MAX_TOTAL_CHARS = 60000", "ALLOWED_TEXT_EXT"],
        "FILE_LIMIT_CONTRACT_MISSING",
    )
    require_contains(
        parser,
        ["result_text", "result", "```", "결과 형식을 확인하지 못했습니다."],
        "PARSER_FAIL_SAFE_CONTRACT_MISSING",
    )
    require_contains(
        box6_client + box4_client + form_modal + review_modal,
        ['role="dialog"', 'aria-modal="true"', "Escape", "previous?.focus()", "uiSafeSidecarErrorMessage", "safeExcerpt"],
        "MODAL_ACCESSIBILITY_OR_REDACTION_MISSING",
    )
    require_contains(
        tests,
        ["card_mode')).toBe('6')", "card_mode') === '4'", "unsupported_type", "too_many", "toHaveLength(0)"],
        "REGRESSION_TEST_CONTRACT_MISSING",
    )

    for rel in STATIC_SCAN_FILES:
        source = read(rel)
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
