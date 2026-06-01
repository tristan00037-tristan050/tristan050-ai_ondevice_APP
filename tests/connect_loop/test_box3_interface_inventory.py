from butler_pc_core.cards.box3.adapters.helper3_format_adapter import apply_format_contract
from butler_pc_core.cards.box3.adapters.helper4_grounding_adapter import verify_grounding
from butler_pc_core.cards.box3.adapters.helper7_extract_adapter import extract_evidence_units
from butler_pc_core.cards.box3.adapters.helper8_style_adapter import apply_style_contract


def test_helper_wrappers_have_contract_samples_without_real_claim():
    units = extract_evidence_units(["digest-safe table <table>x</table>"])
    citations = [
        {
            "source_digest": units[0].source_digest,
            "evidence_unit_digest": units[0].unit_digest,
            "support_level": "supported",
        }
    ]
    grounding, fail_class = verify_grounding(citations=citations, evidence_units=units)
    assert fail_class is None
    assert grounding["source_digest_coverage"] == 1.0
    formatted = apply_format_contract(
        "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"
    )
    assert formatted["required_sections_present"] is True
    style = apply_style_contract("합니다. 확인 필요.")
    assert style["forbidden_style_zero"] is True
    assert style["style_match_score"] >= 0.70

