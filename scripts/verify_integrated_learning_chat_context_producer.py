#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

PRODUCER_FILE = "butler_pc_core/learning_adapters/chat_context_producer.py"
COMMON_FILE = "butler_pc_core/learning_adapters/producer_common.py"
CONTRACT_FILE = "butler_pc_core/learning_core/contracts.py"
SCHEMA_FILE = "schemas/learning/integrated_learning_candidate_v1.schema.json"
EXPECTED_PAYLOAD_KEYS = {
    "explicit_business_confirmation",
    "manager_or_admin_approved",
    "shadow_eval_cases",
    "pii_zero",
    "false_learning_zero",
    "context_digest",
}
EXPECTED_VERIFIED_BY = {
    "group_a",
    "integrated_learning_verifier",
    "privacy_officer",
    "security_reviewer",
}
EXPECTED_CORE_VERIFIED_BY = {
    "group_a",
    "admin",
    "manager",
    "system_contract",
    "integrated_learning_verifier",
    "privacy_officer",
    "security_reviewer",
}
EXPECTED_DROP_REASONS = {
    "CHAT_CONTEXT_DISABLED",
    "BUSINESS_CONFIRMATION_REQUIRED",
    "MANAGER_APPROVAL_REQUIRED",
    "SHADOW_EVAL_CASES_TOO_LOW",
    "PII_NOT_ZERO",
    "FALSE_LEARNING_NOT_ZERO",
    "CONTEXT_DIGEST_INVALID",
    "EVIDENCE_DIGEST_INVALID",
    "VERIFIED_BY_INVALID",
    "VERIFIED_AT_INVALID",
    "EVIDENCE_REF_INVALID",
    "EVIDENCE_REPORT_BINDING_REQUIRED",
    "EVIDENCE_REPORT_BINDING_INVALID",
    "FIXTURE_MODE_FORBIDDEN",
    "RUN_MODE_INVALID",
    "SOURCE_REF_INVALID",
    "SCHEMA_KEYS_INVALID",
}
EXPECTED_RUN_MODES = {"production", "integration", "fixture_test"}
EXPECTED_SHADOW_EVAL_LABELS = {"LEARN", "EXCLUDE", "BLOCK", "DROP"}
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
    "user_name",
    "message_text",
    "conversation_text",
    "account_number_plain",
    "customer_name",
    "peer_chat",
    "messenger",
    "slack",
    "kakao",
    "email_plain",
    "phone_plain",
    "timestamp_raw",
)
FORBIDDEN_DEFAULT_INJECTION_PATTERNS = (
    'data.get("verified_by",',
    "data.get('verified_by',",
    'data.get("verified_at",',
    "data.get('verified_at',",
    'data.get("evidence_ref",',
    "data.get('evidence_ref',",
    'data.get("evidence_digest",',
    "data.get('evidence_digest',",
)
FORBIDDEN_FALLBACK_GREP_PATTERNS = (
    "evidence_digest or",
    "or context_digest",
    "or payload_digest",
    "DEFAULT_EVIDENCE_DIGEST",
)


def _add_failure(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)


def _literal_value(node: ast.AST):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset" and len(node.args) == 1:
        return frozenset(ast.literal_eval(node.args[0]))
    return ast.literal_eval(node)


def _literal_assignments(tree: ast.AST) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = _literal_value(node.value)
                except Exception:
                    continue
    return values


def _name_in_tree(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(child, ast.Name) and child.id in names for child in ast.walk(node))


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        values: set[str] = set()
        for item in target.elts:
            values.update(_target_names(item))
        return values
    return set()


def _has_static_fallback(tree: ast.AST) -> bool:
    fallback_names = {"context_digest", "payload_digest"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = set().union(*(_target_names(target) for target in node.targets))
            if "evidence_digest" in target_names and isinstance(node.value, ast.BoolOp):
                return True
        if isinstance(node, ast.BoolOp) and _name_in_tree(node, fallback_names):
            return True
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "data"
                and node.func.attr == "get"
                and len(node.args) > 1
            ):
                return True
    return False


def _class_annotation_names(tree: ast.AST, class_name: str) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        names: set[str] = set()
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                names.add(child.target.id)
        return names
    return set()


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    failures: list[str] = []

    common = repo / COMMON_FILE
    if not common.exists():
        _add_failure(failures, "COMMON_HELPER_MISSING")
    else:
        common_text = common.read_text(encoding="utf-8")
        if "def bool_field" not in common_text or "isinstance(value, bool)" not in common_text:
            _add_failure(failures, "STRICT_BOOL_HELPER_MISSING")
        if "def int_field" not in common_text or "type(value) is not int" not in common_text:
            _add_failure(failures, "STRICT_INT_HELPER_MISSING")
        if "SOURCE_REFS_NOT_SEQUENCE" not in common_text or "SOURCE_REF_NOT_OBJECT" not in common_text:
            _add_failure(failures, "SOURCE_REFS_FAIL_CLOSED_MISSING")
        if "runner.ingest(candidate)" not in common_text:
            _add_failure(failures, "RUNNER_INGEST_HELPER_MISSING")
        if "ARTIFACT_UNKNOWN_FIELD:" in common_text or "FORBIDDEN_FIELD:" in common_text:
            _add_failure(failures, "DROP_REASON_DETAIL_FORBIDDEN")

    contract = repo / CONTRACT_FILE
    if not contract.exists():
        _add_failure(failures, "CONTRACT_MISSING")
    else:
        contract_text = contract.read_text(encoding="utf-8")
        if '"evidence_report_sha256"' not in contract_text or "EVIDENCE_REPORT_BINDING_INVALID" not in contract_text:
            _add_failure(failures, "EVIDENCE_REPORT_CONTRACT_MISSING")
        if "vault|keyring)://[^\\s]{1,240}" not in contract_text or "sha256:[0-9a-f]{64}" not in contract_text:
            _add_failure(failures, "EVIDENCE_REF_CONTRACT_SCOPE_DRIFT")
        try:
            contract_tree = ast.parse(contract_text)
            contract_values = _literal_assignments(contract_tree)
            if values := contract_values.get("ALLOWED_VERIFIED_BY"):
                if values != frozenset(EXPECTED_CORE_VERIFIED_BY):
                    _add_failure(failures, "CORE_VERIFIED_BY_SCOPE_MISMATCH")
            else:
                _add_failure(failures, "CORE_VERIFIED_BY_SCOPE_MISMATCH")
        except SyntaxError:
            _add_failure(failures, "CONTRACT_SYNTAX_INVALID")

    schema = repo / SCHEMA_FILE
    if not schema.exists():
        _add_failure(failures, "SCHEMA_MISSING")
    else:
        schema_text = schema.read_text(encoding="utf-8")
        if '"evidence_report_sha256"' not in schema_text:
            _add_failure(failures, "SCHEMA_EVIDENCE_REPORT_FIELD_MISSING")
        for role in EXPECTED_CORE_VERIFIED_BY:
            if f'"{role}"' not in schema_text:
                _add_failure(failures, "SCHEMA_VERIFIED_BY_SCOPE_MISMATCH")
                break
        if "sha256:[0-9a-f]{64}" not in schema_text or "vault|keyring)://[^\\\\s]{1,240}" not in schema_text:
            _add_failure(failures, "SCHEMA_EVIDENCE_REF_SCOPE_MISMATCH")

    producer = repo / PRODUCER_FILE
    if not producer.exists():
        _add_failure(failures, "PRODUCER_MISSING")
    else:
        text = producer.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            _add_failure(failures, "PRODUCER_SYNTAX_INVALID")
            tree = None

        if tree is not None:
            values = _literal_assignments(tree)
            if values.get("TARGET_KIND") != "chat_context":
                _add_failure(failures, "TARGET_KIND_MISMATCH")
            if values.get("LEARNING_SOURCE_TYPE") != "verified_chat_context":
                _add_failure(failures, "SOURCE_TYPE_MISMATCH")
            if values.get("PRODUCER_VERSION") != "chat_context_producer.v1.0.0":
                _add_failure(failures, "PRODUCER_VERSION_INVALID")
            if values.get("PAYLOAD_KEYS") != frozenset(EXPECTED_PAYLOAD_KEYS):
                _add_failure(failures, "PAYLOAD_KEYS_MISMATCH")
            if values.get("ALLOWED_CHAT_SOURCE_REF_TYPES") != frozenset({"usage_log", "approval"}):
                _add_failure(failures, "SOURCE_REF_SCOPE_MISMATCH")
            if values.get("ALLOWED_VERIFIED_BY") != frozenset(EXPECTED_VERIFIED_BY):
                _add_failure(failures, "VERIFIED_BY_SCOPE_MISMATCH")
            if values.get("ALLOWED_DROP_REASONS") != frozenset(EXPECTED_DROP_REASONS):
                _add_failure(failures, "DROP_REASON_ENUM_MISMATCH")
            if values.get("ALLOWED_RUN_MODES") != frozenset(EXPECTED_RUN_MODES):
                _add_failure(failures, "RUN_MODE_ENUM_MISMATCH")
            if values.get("SHADOW_EVAL_LABELS") != frozenset(EXPECTED_SHADOW_EVAL_LABELS):
                _add_failure(failures, "SHADOW_EVAL_LABEL_ENUM_MISMATCH")
            artifact_fields = _class_annotation_names(tree, "ChatContextLearningArtifact")
            if "fixture_mode" in artifact_fields or "run_mode" in artifact_fields:
                _add_failure(failures, "RUNTIME_MODE_ARTIFACT_FIELD_FORBIDDEN")
            if _has_static_fallback(tree):
                _add_failure(failures, "CONTRACT_STATIC_VERIFIER_FAIL")

        required_snippets = (
            "ensure_no_forbidden_keys(data)",
            "ensure_exact_fields(data, ChatContextLearningArtifact)",
            "bool_field(",
            "int_field(data, \"shadow_eval_cases\", \"SCHEMA_KEYS_INVALID\")",
            "source_refs_from_mapping(data)",
            "normalize_source_refs(",
            "fallback_type=\"usage_log\"",
            "set(payload) != PAYLOAD_KEYS",
            "validate_verified_by(data[\"verified_by\"] if \"verified_by\" in data else None)",
            "validate_verified_at(data[\"verified_at\"] if \"verified_at\" in data else None)",
            "_reject_runtime_mode_keys(data)",
            "validate_evidence_ref(",
            "run_mode=normalized_run_mode",
            "_require_evidence_digest(",
            "_validate_evidence_report_binding(",
            "EVIDENCE_REPORT_BINDING_REQUIRED",
            "candidate[\"verification\"][\"evidence_report_sha256\"] = item.evidence_report_sha256",
            "classify_chat_context_shadow_eval_label(",
            "RFC3339_UTC_RE.fullmatch",
            "datetime.strptime",
            "EVIDENCE_REF_DENY_RE.search",
            "EVIDENCE_REF_ALLOW_RE.fullmatch",
            "build_candidate_envelope(",
            "ingest_candidate(candidate, runner)",
        )
        for snippet in required_snippets:
            if snippet not in text:
                _add_failure(failures, "REQUIRED_GUARD_MISSING")
                break
        if any(term in text for term in FORBIDDEN_DIRECT_CALLS):
            _add_failure(failures, "QUEUE_DIRECT_APPEND_FORBIDDEN")
        if "print(" in text or "repr(" in text or "traceback" in text or "format_exc" in text:
            _add_failure(failures, "UNSAFE_OUTPUT_FORBIDDEN")
        if "ARTIFACT_UNKNOWN_FIELD:" in text or "FORBIDDEN_FIELD:" in text or ("_fail(f" in text and ":{" in text):
            _add_failure(failures, "DROP_REASON_DETAIL_FORBIDDEN")
        if any(pattern in text for pattern in FORBIDDEN_DEFAULT_INJECTION_PATTERNS):
            _add_failure(failures, "CONTRACT_STATIC_VERIFIER_FAIL")
        if any(pattern in text for pattern in FORBIDDEN_FALLBACK_GREP_PATTERNS):
            _add_failure(failures, "CONTRACT_STATIC_VERIFIER_FAIL")
        if "if raw_value is None:\n        return None" in text:
            _add_failure(failures, "EVIDENCE_REPORT_BINDING_REQUIRED_BYPASS")
        if "fixture_mode: bool" in text:
            _add_failure(failures, "RUNTIME_MODE_ARTIFACT_FIELD_FORBIDDEN")
        if "verified_by=str(" in text or "verified_at=str(" in text or "evidence_ref=str(" in text:
            _add_failure(failures, "PROVENANCE_STRING_CAST_FORBIDDEN")
        for term in FORBIDDEN_OUTPUT_TERMS:
            if term in text:
                _add_failure(failures, "RAW_OUTPUT_TERM_FORBIDDEN")
                break

    if failures:
        print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0")
        for failure in failures:
            print(f"ERROR_CODE={failure}")
        return 1
    print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
