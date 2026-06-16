from __future__ import annotations

from pathlib import Path

import pytest

from butler_pc_core.company_fact import storage
from butler_pc_core.company_fact.extractor import (
    EvidenceUnitRuntime,
    extract_company_fact_candidate,
    sha256_text,
)


ROOT = Path(__file__).resolve().parents[2]


def _unit() -> EvidenceUnitRuntime:
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "출처: 사내규정\n"
    )
    return EvidenceUnitRuntime(
        unit_id="u1",
        text_runtime_only=text,
        source_digest=sha256_text("source"),
        unit_digest=sha256_text(text),
        unit_kind="qa",
        order=0,
    )


def test_extractor_source_contains_no_http_store_or_endpoint_calls():
    source = (ROOT / "butler_pc_core" / "company_fact" / "extractor.py").read_text(encoding="utf-8")
    forbidden = [
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.",
        "CompanyFactStore",
        "save_candidate",
        "approve_candidate",
        "/v1/company-facts/candidates",
    ]

    assert not any(item in source for item in forbidden)


def test_extractor_does_not_call_store_mutation_methods(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise AssertionError("SIDE_EFFECT_BLOCKED")

    monkeypatch.setattr(storage.CompanyFactStore, "save_candidate", _blocked)
    monkeypatch.setattr(storage.CompanyFactStore, "approve_candidate", _blocked)

    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit()])

    assert outcome.status == "draft_ready"
    assert outcome.auto_submit_zero is True
    assert outcome.approve_called_zero is True


def test_extractor_has_no_resolver_exposure_path():
    source = (ROOT / "butler_pc_core" / "company_fact" / "extractor.py").read_text(encoding="utf-8")

    assert "CompanyKnowledgeResolver" not in source
    assert "resolve(" not in source
