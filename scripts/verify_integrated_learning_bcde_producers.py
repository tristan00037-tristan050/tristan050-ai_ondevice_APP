#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

PRODUCER_FILES = {
    "policy_rule": "butler_pc_core/learning_adapters/policy_rule_producer.py",
    "company_format": "butler_pc_core/learning_adapters/company_format_producer.py",
    "approved_fact": "butler_pc_core/learning_adapters/approved_fact_producer.py",
    "folder_doc": "butler_pc_core/learning_adapters/folder_doc_producer.py",
}
EXPECTED_SOURCE_TYPES = {
    "policy_rule": "verified_policy_rule",
    "company_format": "verified_company_format",
    "approved_fact": "verified_approved_fact",
    "folder_doc": "verified_folder_doc",
}
COMMON_FILE = "butler_pc_core/learning_adapters/producer_common.py"
FORBIDDEN_DIRECT_CALLS = ("ArtifactQueue", ".append_candidate(")
FORBIDDEN_OUTPUT_TERMS = (
    "raw_memo",
    "policy_text",
    "policy_body",
    "template_body",
    "template_text",
    "fact_text",
    "folder_content",
    "file_content",
    "document_text",
    "file_path",
    "local_path",
    "prompt",
    "response_text",
    "account_number_plain",
)


def _add_failure(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)


def _literal_assignments(tree: ast.AST) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception:
                    continue
    return values


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    failures: list[str] = []
    texts: dict[str, str] = {}

    common = repo / COMMON_FILE
    if not common.exists():
        _add_failure(failures, "COMMON_HELPER_MISSING")
    else:
        common_text = common.read_text(encoding="utf-8")
        if "def bool_field" not in common_text or "isinstance(value, bool)" not in common_text:
            _add_failure(failures, "STRICT_BOOL_HELPER_MISSING")
        if "SOURCE_REFS_NOT_SEQUENCE" not in common_text or "SOURCE_REF_NOT_OBJECT" not in common_text:
            _add_failure(failures, "SOURCE_REFS_FAIL_CLOSED_MISSING")
        if "runner.ingest(candidate)" not in common_text:
            _add_failure(failures, "RUNNER_INGEST_HELPER_MISSING")
        if "ARTIFACT_UNKNOWN_FIELD:" in common_text or "FORBIDDEN_FIELD:" in common_text:
            _add_failure(failures, "DROP_REASON_DETAIL_FORBIDDEN")

    for target_kind, rel in PRODUCER_FILES.items():
        path = repo / rel
        if not path.exists():
            _add_failure(failures, "PRODUCER_MISSING")
            continue
        text = path.read_text(encoding="utf-8")
        texts[target_kind] = text
        try:
            tree = ast.parse(text)
        except SyntaxError:
            _add_failure(failures, "PRODUCER_SYNTAX_INVALID")
            continue
        values = _literal_assignments(tree)
        if values.get("TARGET_KIND") != target_kind:
            _add_failure(failures, "TARGET_KIND_MISMATCH")
        if values.get("LEARNING_SOURCE_TYPE") != EXPECTED_SOURCE_TYPES[target_kind]:
            _add_failure(failures, "SOURCE_TYPE_MISMATCH")
        if not isinstance(values.get("PRODUCER_VERSION"), str) or not values["PRODUCER_VERSION"].endswith("_producer.v1.0.0"):
            _add_failure(failures, "PRODUCER_VERSION_INVALID")
        if "PAYLOAD_KEYS = frozenset(" not in text or "set(payload) != PAYLOAD_KEYS" not in text:
            _add_failure(failures, "PAYLOAD_EXACT_KEYS_MISSING")
        if "ingest_candidate(candidate, runner)" not in text:
            _add_failure(failures, "RUNNER_INGEST_PATH_MISSING")
        if any(term in text for term in FORBIDDEN_DIRECT_CALLS):
            _add_failure(failures, "QUEUE_DIRECT_APPEND_FORBIDDEN")
        if "print(" in text or "repr(" in text:
            _add_failure(failures, "UNSAFE_OUTPUT_FORBIDDEN")
        if "source_refs_from_mapping(data)" not in text:
            _add_failure(failures, "SOURCE_REFS_COERCE_MISSING")
        if "ARTIFACT_FIELD_REQUIRED:" in text or ("_fail(f" in text and ":{" in text):
            _add_failure(failures, "ARTIFACT_FIELD_REQUIRED_DETAIL_FORBIDDEN")

    # Producer modules must not define raw-carrying field names themselves. The
    # common helper is allowed to list forbidden keys because it enforces them.
    for text in texts.values():
        for term in FORBIDDEN_OUTPUT_TERMS:
            if term in text:
                _add_failure(failures, "RAW_OUTPUT_TERM_FORBIDDEN")
                break

    if failures:
        print("BCDE_PRODUCER_CONTRACT_OK=0")
        for failure in failures:
            print(f"ERROR_CODE={failure}")
        return 1
    print("BCDE_PRODUCER_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
