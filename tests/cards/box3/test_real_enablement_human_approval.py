from __future__ import annotations

from datetime import datetime, timezone

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig, evaluate_human_approval
from butler_pc_core.cards.box3.real_contracts import sha256_text


def test_missing_approval_is_not_allowed():
    verdict = evaluate_human_approval(HumanApprovalConfig(kill_switch_enabled=False))
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_MISSING"


def test_valid_approval_passes_scope():
    scope = sha256_text("scope")
    cfg = HumanApprovalConfig(
        allow=True,
        approved_by_digest=sha256_text("admin"),
        approval_scope_digest=scope,
        approved_at="2026-06-01T00:00:00Z",
        expires_at="2026-12-31T00:00:00Z",
        revoked=False,
        kill_switch_enabled=False,
    )
    verdict = evaluate_human_approval(cfg, expected_scope_digest=scope, now=datetime(2026, 6, 3, tzinfo=timezone.utc))
    assert verdict.allowed is True
    assert verdict.fail_class is None


def test_kill_switch_blocks_even_if_allow_true():
    scope = sha256_text("scope")
    cfg = HumanApprovalConfig(
        allow=True,
        approved_by_digest=sha256_text("admin"),
        approval_scope_digest=scope,
        approved_at="2026-06-01T00:00:00Z",
        expires_at="2026-12-31T00:00:00Z",
        revoked=False,
        kill_switch_enabled=True,
    )
    verdict = evaluate_human_approval(cfg, expected_scope_digest=scope, now=datetime(2026, 6, 3, tzinfo=timezone.utc))
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_KILL_SWITCH"
