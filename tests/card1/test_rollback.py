from pathlib import Path

from src.butler.card1.safety.rollback import build_rollback_evidence, load_rollback_evidence, write_rollback_evidence


def test_build_rollback_evidence_detects_change():
    evidence = build_rollback_evidence(
        previous_text="old allowlist",
        new_text="new allowlist",
        change_summary="update Card 1 allowlist contract",
    )

    assert evidence.card_id == "card1_request_core_extraction"
    assert evidence.previous_sha256 != evidence.new_sha256
    assert evidence.rollback_required is True


def test_build_rollback_evidence_no_change_no_rollback():
    evidence = build_rollback_evidence(
        previous_text="same",
        new_text="same",
        change_summary="no-op contract check",
    )

    assert evidence.previous_sha256 == evidence.new_sha256
    assert evidence.rollback_required is False


def test_rollback_evidence_roundtrip(tmp_path: Path):
    evidence = build_rollback_evidence(
        previous_text="old",
        new_text="new",
        change_summary="roundtrip",
    )
    path = tmp_path / "rollback.json"
    write_rollback_evidence(evidence, path)
    loaded = load_rollback_evidence(path)

    assert loaded["card_id"] == "card1_request_core_extraction"
    assert loaded["rollback_required"] is True
