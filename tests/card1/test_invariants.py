from src.butler.card1.safety.invariants import INVARIANT_NAMES, validate_six_invariants


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


def test_six_invariant_names_are_locked():
    assert INVARIANT_NAMES == (
        "output_is_object",
        "intent_present",
        "deadline_requires_digest",
        "auto_apply_guarded",
        "content_not_retained_flag",
        "no_external_egress_flag",
    )


def test_six_invariants_accept_valid_output():
    report = validate_six_invariants(_valid_output())
    assert report.ok is True
    assert report.blocked is False


def test_six_invariants_block_deadline_without_digest():
    out = _valid_output()
    out.pop("source_digest16")
    report = validate_six_invariants(out)
    assert report.blocked is True
    assert "deadline_requires_digest" in report.violations


def test_six_invariants_block_low_confidence_auto_apply():
    out = _valid_output()
    out["confidence"] = 0.5
    report = validate_six_invariants(out)
    assert report.blocked is True
    assert "auto_apply_guarded" in report.violations


def test_six_invariants_block_missing_policy_flags():
    out = _valid_output()
    out["policy_flags"] = []
    report = validate_six_invariants(out)
    assert report.blocked is True
    assert "content_not_retained_flag" in report.violations
    assert "no_external_egress_flag" in report.violations
