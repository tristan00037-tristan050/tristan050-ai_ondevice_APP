"""factpack_rules.py — D-4 Card 2 사실팩 위반 규칙.

매핑 결과·출력 문서를 검사해 5종 fail class 위반을 fail-closed 로 탐지한다.
원문 텍스트는 검사 대상에 보존하지 않으며 메타·digest 만 다룬다.
"""
from __future__ import annotations

import re
from typing import Optional

# ── 필수 fail class 5종 ──────────────────────────────────────────────────────
SOURCE_FACT_MISSING = "SOURCE_FACT_MISSING"
SOURCE_CITATION_MISSING = "SOURCE_CITATION_MISSING"
TEMPLATE_PLACEHOLDER_RESIDUE = "TEMPLATE_PLACEHOLDER_RESIDUE"
UNSUPPORTED_FACT_MAPPING = "UNSUPPORTED_FACT_MAPPING"
WIKI_ONLY_FACT_NOT_AUTOFILLABLE = "WIKI_ONLY_FACT_NOT_AUTOFILLABLE"

FAIL_CLASSES = frozenset({
    SOURCE_FACT_MISSING,
    SOURCE_CITATION_MISSING,
    TEMPLATE_PLACEHOLDER_RESIDUE,
    UNSUPPORTED_FACT_MAPPING,
    WIKI_ONLY_FACT_NOT_AUTOFILLABLE,
})

# 양식 placeholder 잔류 패턴 (auto_fill 후에도 남으면 위반)
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\[\[[^\]]+\]\]|＿{2,}|__{2,}")


def check_source_fact_present(mapping) -> Optional[str]:
    """source_fact_id 부재 → SOURCE_FACT_MISSING."""
    if not getattr(mapping, "source_fact_id", None):
        return SOURCE_FACT_MISSING
    return None


def check_source_citation(mapping) -> Optional[str]:
    """auto_fill/review 인데 citation 부재 → SOURCE_CITATION_MISSING."""
    if getattr(mapping, "decision", "") in ("auto_fill", "review"):
        if not getattr(mapping, "citation", None):
            return SOURCE_CITATION_MISSING
    return None


def check_unsupported_mapping(mapping) -> Optional[str]:
    """factpack_ok=False 인데 auto_fill → UNSUPPORTED_FACT_MAPPING."""
    if getattr(mapping, "decision", "") == "auto_fill" and not getattr(
            mapping, "factpack_ok", True):
        return UNSUPPORTED_FACT_MAPPING
    return None


def check_wiki_only_autofill(mapping, source_facts) -> Optional[str]:
    """wiki_only 사실이 auto_fill → WIKI_ONLY_FACT_NOT_AUTOFILLABLE."""
    by_id = {f.fact_id: f for f in source_facts}
    fact = by_id.get(getattr(mapping, "source_fact_id", None))
    if (fact is not None and getattr(fact, "wiki_only", False)
            and getattr(mapping, "decision", "") == "auto_fill"):
        return WIKI_ONLY_FACT_NOT_AUTOFILLABLE
    return None


def check_template_placeholder_residue(rendered_text: str) -> Optional[str]:
    """출력 문서에 미치환 placeholder 잔류 → TEMPLATE_PLACEHOLDER_RESIDUE."""
    if rendered_text and _PLACEHOLDER_RE.search(rendered_text):
        return TEMPLATE_PLACEHOLDER_RESIDUE
    return None


def audit_factpack(mappings, source_facts, rendered_text: str = "") -> dict:
    """매핑 + 출력 문서 전수 검사 → 위반 목록. fail_count 0 이 PASS."""
    violations = []
    for m in mappings:
        for checker in (check_source_citation, check_unsupported_mapping):
            fc = checker(m)
            if fc:
                violations.append({"slot_id": m.slot_id, "fail_class": fc})
        fc = check_wiki_only_autofill(m, source_facts)
        if fc:
            violations.append({"slot_id": m.slot_id, "fail_class": fc})
    residue = check_template_placeholder_residue(rendered_text)
    if residue:
        violations.append({"slot_id": None, "fail_class": residue})
    return {
        "fail_count": len(violations),
        "violations": violations,
        "fail_classes_known": sorted(FAIL_CLASSES),
        "passed": len(violations) == 0,
    }
