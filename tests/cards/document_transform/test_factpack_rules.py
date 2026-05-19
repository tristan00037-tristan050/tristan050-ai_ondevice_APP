"""test_factpack_rules.py — D-4 Card 2 factpack 5 fail class 8건 (M-60 신규)."""
from __future__ import annotations

from butler_pc_core.cards.document_transform import factpack_rules as fr
from butler_pc_core.cards.document_transform.mapper import SlotMapping, SourceFact


def _m(**kw):
    base = dict(slot_id="s1", source_fact_id="f1", confidence=0.9,
                decision="auto_fill", citation="ext:doc#1", factpack_ok=True)
    base.update(kw)
    return SlotMapping(**base)


def test_five_fail_classes_defined():
    assert fr.FAIL_CLASSES == frozenset({
        "SOURCE_FACT_MISSING", "SOURCE_CITATION_MISSING",
        "TEMPLATE_PLACEHOLDER_RESIDUE", "UNSUPPORTED_FACT_MAPPING",
        "WIKI_ONLY_FACT_NOT_AUTOFILLABLE",
    })


def test_source_fact_missing():
    assert fr.check_source_fact_present(_m(source_fact_id=None)) == "SOURCE_FACT_MISSING"
    assert fr.check_source_fact_present(_m()) is None


def test_source_citation_missing():
    assert fr.check_source_citation(_m(citation=None)) == "SOURCE_CITATION_MISSING"
    assert fr.check_source_citation(_m(decision="blank", citation=None)) is None


def test_unsupported_fact_mapping():
    assert fr.check_unsupported_mapping(_m(factpack_ok=False)) == "UNSUPPORTED_FACT_MAPPING"
    assert fr.check_unsupported_mapping(_m()) is None


def test_template_placeholder_residue():
    assert fr.check_template_placeholder_residue("보고서 {{slot}}") == "TEMPLATE_PLACEHOLDER_RESIDUE"
    assert fr.check_template_placeholder_residue("보고서 완성") is None


def test_wiki_only_fact_not_autofillable():
    wiki = SourceFact(fact_id="f1", label="x", value="1", citation="wiki:Q", wiki_only=True)
    assert fr.check_wiki_only_autofill(_m(), [wiki]) == "WIKI_ONLY_FACT_NOT_AUTOFILLABLE"
    normal = SourceFact(fact_id="f1", label="x", value="1", citation="ext:1", wiki_only=False)
    assert fr.check_wiki_only_autofill(_m(), [normal]) is None


def test_audit_factpack_clean_pass():
    res = fr.audit_factpack([_m()], [SourceFact(fact_id="f1", label="x", value="1",
                            citation="ext:1")], "완성 문서")
    assert res["passed"] is True and res["fail_count"] == 0


def test_audit_factpack_detects_violations():
    bad = _m(factpack_ok=False)
    res = fr.audit_factpack([bad], [SourceFact(fact_id="f1", label="x", value="1",
                            citation="ext:1")], "보고서 {{unfilled}}")
    assert res["passed"] is False
    classes = {v["fail_class"] for v in res["violations"]}
    assert "UNSUPPORTED_FACT_MAPPING" in classes
    assert "TEMPLATE_PLACEHOLDER_RESIDUE" in classes
