from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.actual_contracts import assert_persistable_digest_only, sha256_text
from butler_pc_core.cards.box3.human_approval_sealed import evaluate_human_approval_sealed


def test_persistable_dict_rejects_raw_and_path():
    with pytest.raises(AssertionError):
        assert_persistable_digest_only({"draft_text": "raw", "path": "/" + "Users/example/model.gguf"})


def test_human_approval_default_locked():
    scope = sha256_text("scope")
    verdict = evaluate_human_approval_sealed(None, expected_scope_digest=scope)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_MISSING"


def test_request_body_cannot_approve_without_scope_binding():
    scope = sha256_text("scope")
    verdict = evaluate_human_approval_sealed({"allow": True, "kill_switch_enabled": False}, expected_scope_digest=scope)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH"
