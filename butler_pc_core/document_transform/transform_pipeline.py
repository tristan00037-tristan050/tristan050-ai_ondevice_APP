"""transform_pipeline.py — 문서 변환 전체 파이프라인."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .content_extractor import extract_text_from_bytes
from .template_parser import TemplateSection, parse_template_bytes
from .output_renderer import render_docx_bytes, render_md_text


@dataclass
class MappedSection:
    heading: str
    level: int
    content: str
    mapped: bool


@dataclass
class TransformResult:
    confidence: float                     # 0.0 ~ 1.0
    mapped_sections: List[MappedSection]
    unmapped_sections: List[str]          # 양식에는 있으나 외부 문서에 내용 없는 섹션
    output_docx_bytes: bytes
    output_md: str


# ── 의미 영역별 동의어 그룹 (섹션 heading → 외부 문서 키워드 매핑) ─────────────
# "영역" 그룹에 "협업"을 포함하지 않음 — 협업은 별도 항목
_SYNONYM_GROUPS: list[tuple[str, list[str]]] = [
    ("기간",   ["기한", "duration", "period", "개월", "months", "주간", "연간", "년간"]),
    ("예산",   ["금액", "budget", "비용", "fee", "요금", "cost", "price", "가격", "견적"]),
    ("일정",   ["시작일", "착수일", "schedule", "날짜", "date", "종료일", "완료일", "마감일"]),
    ("연락처", ["이메일", "email", "전화", "phone", "tel", "contact", "담당자", "수신인"]),
    ("영역",   ["분야", "scope", "범위", "역할", "업무", "서비스"]),
    ("개요",   ["요약", "summary", "overview", "소개", "배경", "목적", "제안", "목표"]),
    ("계약",   ["agreement", "contract", "협약", "협정"]),
    ("효과",   ["기대효과", "성과", "result", "outcome", "이점", "benefit"]),
]

# 빠른 조회를 위한 역방향 맵: 임의 키워드 → 해당 그룹의 모든 동의어
_KEYWORD_TO_SYNONYMS: dict[str, set[str]] = {}
for _master, _syns in _SYNONYM_GROUPS:
    _group = {_master} | set(_syns)
    for _kw in _group:
        _KEYWORD_TO_SYNONYMS.setdefault(_kw, set()).update(_group)


def transform_document(
    external_data: bytes,
    external_suffix: str,
    template_data: bytes,
    template_suffix: str,
    include_source_note: bool = False,
    llm=None,
) -> TransformResult:
    """외부 문서 + 우리 양식 → TransformResult."""
    external_text = extract_text_from_bytes(external_data, external_suffix)
    template_sections = parse_template_bytes(template_data, template_suffix)

    if llm is not None and getattr(llm, "status", "") == "ready":
        mapped = _map_with_llm(external_text, template_sections, llm)
    else:
        mapped = _map_heuristic(external_text, template_sections)

    unmapped = [s.heading for s in mapped if not s.mapped]
    total = len(mapped)
    mapped_count = total - len(unmapped)
    confidence = round(mapped_count / total, 2) if total > 0 else 0.0

    sections_dicts = [
        {"heading": s.heading, "level": s.level, "content": s.content, "mapped": s.mapped}
        for s in mapped
    ]

    if include_source_note:
        sections_dicts.append({
            "heading": "출처 원본",
            "level": 2,
            "content": "_(원본 문서에서 추출됨)_",
            "mapped": True,
        })

    return TransformResult(
        confidence=confidence,
        mapped_sections=mapped,
        unmapped_sections=unmapped,
        output_docx_bytes=render_docx_bytes(sections_dicts),
        output_md=render_md_text(sections_dicts),
    )


# ── 텍스트 분리 ──────────────────────────────────────────────────────────────

def _split_items(text: str) -> list[str]:
    """
    외부 문서를 의미 단위 항목으로 분리.
    - 번호 목록("1. xxx"), 불릿("- xxx"), 콜론 키-값("key: value") → 줄 단위
    - 일반 문단 → 이중 개행 단위
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    numbered_re = re.compile(r"^\d+[\.\)]\s+")
    bullet_re = re.compile(r"^[-*•]\s+")
    colon_re = re.compile(r"^[^:\n]{1,30}:\s*\S")

    line_list_count = sum(
        1 for l in lines
        if numbered_re.match(l) or bullet_re.match(l) or colon_re.match(l)
    )

    # 절반 이상이 목록/KV 형식이면 줄 단위 분리
    if line_list_count >= max(1, len(lines) / 2):
        return lines

    # 이중 개행으로 분리 (일반 문단)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    return paragraphs if len(paragraphs) > 1 else lines


# ── 키워드 추출 + 의미 확장 ──────────────────────────────────────────────────

_STOP_KO = {"및", "의", "와", "과", "을", "를", "이", "가", "에", "도", "로", "은", "는", "하다"}


def _extract_keywords(heading: str) -> set[str]:
    tokens = re.findall(r"[가-힣a-zA-Z]+", heading)
    return {t.lower() for t in tokens if t not in _STOP_KO and len(t) >= 2}


def _expand_keywords(keywords: set[str]) -> set[str]:
    """섹션 키워드를 의미 영역 동의어로 확장 (1단계만, transitivity 없음)."""
    expanded = set(keywords)
    for kw in keywords:
        expanded |= _KEYWORD_TO_SYNONYMS.get(kw, set())
    return expanded


def _keyword_count(expanded: set[str], text: str) -> int:
    """text에서 expanded 키워드와 일치하는 개수 (raw count)."""
    text_lower = text.lower()
    return sum(1 for kw in expanded if kw in text_lower)


# ── 의미 기반 휴리스틱 매핑 ──────────────────────────────────────────────────

def _map_heuristic(
    external_text: str,
    template_sections: List[TemplateSection],
) -> List[MappedSection]:
    """
    섹션-항목 1:1 의미 매핑.
    - 외부 문서를 의미 단위로 분리 (번호 목록 / KV / 문단)
    - 섹션 heading 키워드를 동의어 그룹으로 확장
    - 확장 키워드 raw count ≥ 1 인 경우만 매핑 (강제 매핑 X)
    - 템플릿 순서대로 greedy: 이미 사용된 항목은 제외
    """
    items = _split_items(external_text)
    if not items:
        return [
            MappedSection(heading=s.heading, level=s.level, content="", mapped=False)
            for s in template_sections
        ]

    result: List[MappedSection] = []
    used: set[int] = set()

    for sec in template_sections:
        keywords = _extract_keywords(sec.heading)
        expanded = _expand_keywords(keywords)

        best_idx: Optional[int] = None
        best_score = 0

        for idx, item in enumerate(items):
            if idx in used:
                continue
            score = _keyword_count(expanded, item)
            if score > best_score:
                best_score = score
                best_idx = idx

        # 최소 키워드 1개 이상 일치해야 매핑 (강제 매핑 X)
        if best_idx is not None and best_score >= 1:
            used.add(best_idx)
            result.append(MappedSection(
                heading=sec.heading,
                level=sec.level,
                content=items[best_idx],
                mapped=True,
            ))
        else:
            result.append(MappedSection(
                heading=sec.heading,
                level=sec.level,
                content="",
                mapped=False,
            ))

    return result


# ── LLM 매핑 ─────────────────────────────────────────────────────────────────

def _map_with_llm(
    external_text: str,
    template_sections: List[TemplateSection],
    llm,
) -> List[MappedSection]:
    """LLM 기반 매핑 (실제 LLM 사용 시 — 실패 시 휴리스틱 폴백)."""
    section_headings = "\n".join(
        f"{i+1}. {s.heading}" for i, s in enumerate(template_sections)
    )
    prompt = (
        f"다음 외부 문서를 우리 양식의 각 섹션에 맞게 재구성하세요.\n\n"
        f"[우리 양식 섹션 목록]\n{section_headings}\n\n"
        f"[외부 문서 내용]\n{external_text[:3000]}\n\n"
        f"각 섹션 번호와 해당 내용을 JSON 형식으로 출력하세요: "
        f'[{{"section": 1, "content": "..."}}]'
    )
    try:
        response = llm.generate(prompt, max_tokens=2000)
        import json
        m = re.search(r"\[.*\]", response, re.DOTALL)
        if not m:
            return _map_heuristic(external_text, template_sections)
        items = json.loads(m.group())
        content_map = {item["section"]: item.get("content", "") for item in items if isinstance(item, dict)}
        return [
            MappedSection(
                heading=sec.heading,
                level=sec.level,
                content=content_map.get(i + 1, ""),
                mapped=bool(content_map.get(i + 1, "")),
            )
            for i, sec in enumerate(template_sections)
        ]
    except Exception:
        return _map_heuristic(external_text, template_sections)
