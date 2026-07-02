from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
PRODUCER = ROOT / "butler_pc_core/learning_adapters/chat_context_producer.py"
TESTS = ROOT / "tests/learning_adapters/test_chat_context_producer.py"


def fail(code: str) -> int:
    print(f"CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0 {code}")
    return 1


def main() -> int:
    if not PRODUCER.exists():
        return fail("PRODUCER_MISSING")
    if not TESTS.exists():
        return fail("TESTS_MISSING")
    text = PRODUCER.read_text(encoding="utf-8")
    try:
        ast.parse(text)
    except SyntaxError:
        return fail("PRODUCER_SYNTAX_INVALID")
    required = [
        'PRODUCER_VERSION = "chat_context_producer.v1.0.0"',
        'TARGET_KIND = "chat_context"',
        'LEARNING_SOURCE_TYPE = "verified_chat_context"',
        'PAYLOAD_KEYS = frozenset',
        'ALLOWED_SOURCE_REF_TYPES = frozenset({"usage_log", "approval"})',
        'LearningIntakeRunner',
        'ingest_candidate',
        'digest_safe_drop_summary',
        'bool_field',
        'int_field',
    ]
    for token in required:
        if token not in text:
            return fail("REQUIRED_TOKEN_MISSING")
    forbidden = ["ArtifactQueue", ".append_candidate(", "print(", "repr(", "traceback", "auto_apply_to_runtime=True"]
    for token in forbidden:
        if token in text:
            return fail("FORBIDDEN_TOKEN_PRESENT")
    test_text = TESTS.read_text(encoding="utf-8")
    for name in [
        "test_chat_context_verified_ingest_accepts_with_enable_chat",
        "test_chat_context_default_disabled_drops",
        "test_chat_context_shadow_eval_threshold_and_type_drop",
        "test_chat_context_bool_strings_drop_before_queue",
        "test_chat_context_source_refs_allow_usage_log_and_approval_only",
        "test_chat_context_raw_and_unknown_artifact_fields_drop_without_echo",
        "test_chat_context_queue_idempotent_duplicate",
    ]:
        if name not in test_text:
            return fail("TEST_CASE_MISSING")
    print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
