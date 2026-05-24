from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOX2 = ROOT / "src/ui/cards/Box2DryRunGate.tsx"
BOX3 = ROOT / "src/ui/cards/Box3DryRunGate.tsx"
CLIENT = ROOT / "src/ui/cards/ip3DryRunClient.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_box2_dry_run_gate_has_required_contract():
    source = _read(BOX2)
    assert "actual_model_call=false" in source
    assert "production_hook_deployed=false" in source
    assert "release_claim_allowed=false" in source
    assert "92e8454fdc01d9bb" in source
    assert "sample replay" in source
    assert "IP1 v5.4 forward evidence + IP2 v2.4 live PEP" in source


def test_box3_dry_run_gate_has_required_contract():
    source = _read(BOX3)
    assert "actual_model_call=false" in source
    assert "production_hook_deployed=false" in source
    assert "release_claim_allowed=false" in source
    assert "ad852bbb79aee63c" in source
    assert "sample replay" in source
    assert "반드시 우리 승인 후" in source


def test_ui_client_forces_dry_run_and_no_model_call():
    source = _read(CLIENT)
    assert "http://127.0.0.1:8765/v1/chat/completions" in source
    assert "actual_model_call: false" in source
    assert "production_hook_deployed: false" in source
    assert "release_claim_allowed: false" in source
    assert "evidence_class" in source
    assert "sample_replay" in source


def test_ui_does_not_claim_live_or_production():
    combined = "\n".join([_read(BOX2), _read(BOX3), _read(CLIENT)])
    forbidden = [
        "production_hook_deployed=true",
        "release_claim_allowed=true",
        "runtime_live=true",
        "forward_verified=true",
        "live routing deployed",
        "APPROVED_FOR_PRODUCTION",
    ]
    for item in forbidden:
        assert item not in combined


def test_ui_sample_replay_contains_box2_and_box3_payloads():
    client = _read(CLIENT)
    assert "company_form_sample" in client
    assert "sample_agreement_digest_only" in client
    assert "draft_review_request" in client
    assert "approval_required_text" in client


def test_raw_text_persistence_is_not_implemented_in_ui():
    combined = "\n".join([_read(BOX2), _read(BOX3), _read(CLIENT)])
    forbidden_fragments = [
        "localStorage.setItem",
        "sessionStorage.setItem",
        "indexedDB.open",
        "writeFile",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in combined
