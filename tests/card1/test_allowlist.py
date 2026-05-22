from src.butler.card1.safety.allowlist import load_allowlist, validate_card1_output


def _valid_output():
    return {
        "sample_id": "sample_digest_only_001",
        "intent_type": "REQUEST",
        "deadline_type": "HARD",
        "normalized_action": "send",
        "action_items": ["digest_action_001"],
        "materials": ["digest_material_001"],
        "confidence": 0.96,
        "auto_apply_allowed": True,
        "policy_flags": ["manual_review_only", "auto_apply_off", "deadline_needs_evidence", "content_not_retained", "no_external_egress"],
        "source_digest16": "0123456789abcdef",
    }


def test_load_allowlist_sha_pinned():
    data = load_allowlist()
    assert data["card_id"] == "card1_request_core_extraction"
    assert data["model_card_mapping"] == "tool_call"


def test_allowlist_accepts_valid_card1_output():
    decision = validate_card1_output(_valid_output())
    assert decision.ok is True
    assert decision.blocked is False


def test_allowlist_blocks_unknown_intent():
    out = _valid_output()
    out["intent_type"] = "UNKNOWN"
    decision = validate_card1_output(out)
    assert decision.blocked is True
    assert decision.fail_class == "allowlist_violation"
    assert "intent_type" in decision.violations


def test_allowlist_blocks_extra_field():
    out = _valid_output()
    out["unexpected_field"] = "blocked"
    decision = validate_card1_output(out)
    assert decision.blocked is True
    assert any(v.startswith("unknown_output_fields") for v in decision.violations)
