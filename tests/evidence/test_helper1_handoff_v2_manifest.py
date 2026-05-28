"""Codex P2 regression guard (2026-05-27).

The helper1 v3 sealing manifest had listed negated safety disclosures
("production ready 아님" 등) under ``forbidden_claims``. Per repo convention
(see evidence/card5_lora_v3_3/option_d_manifest_v2.json) forbidden_claims names
the positive unsafe claims that must NOT be made; the negated disclaimers belong
in a separate ``required_disclosures`` field. These tests lock that in.
"""
import json
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "evidence/helper1_handoff_v2/sealing_evidence_v3_correct.json"


@pytest.fixture
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_forbidden_claims_contains_no_negation(manifest):
    """forbidden_claims must list positive unsafe claims, never '아님' disclaimers."""
    forbidden = manifest.get("forbidden_claims", [])
    negations = [c for c in forbidden if isinstance(c, str) and "아님" in c]
    assert not negations, f"forbidden_claims에 negation 잔존: {negations}"


def test_forbidden_claims_lists_unsafe_positive_claims(manifest):
    """The four unsafe positive claims are present in forbidden_claims."""
    forbidden = set(manifest.get("forbidden_claims", []))
    expected = {
        "production ready",
        "회사 전체 기억 AI 완성",
        "BGE-reranker/FAISS 적용 완료",
        "smoke 3/3 PASS 봉인",
    }
    missing = expected - forbidden
    assert not missing, f"forbidden_claims에 positive claim 누락: {missing}"


def test_required_disclosures_contains_negations(manifest):
    """The negated disclaimers are preserved under required_disclosures."""
    disclosures = (
        manifest.get("required_disclosures")
        or manifest.get("safety_disclaimers")
        or manifest.get("limitations_disclosures")
        or []
    )
    negations = [c for c in disclosures if isinstance(c, str) and "아님" in c]
    assert len(negations) >= 4, f"required_disclosures에 negation 보존 부족: {disclosures}"


def test_production_claim_consistency(manifest):
    """A non-production manifest must forbid the 'production ready' positive claim."""
    # 이 manifest는 boundary_zero.production_claim_zero + limitations로 비-production을 선언.
    assert manifest.get("boundary_zero", {}).get("production_claim_zero") is True
    assert any("production ready" in c for c in manifest.get("forbidden_claims", [])), (
        "production 비허용 manifest인데 forbidden_claims에 'production ready' 누락"
    )
