"""transform_pipeline.py — 문서 변환 전체 파이프라인."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .content_extractor import extract_text_from_file, extract_text_from_bytes
from .template_parser import TemplateSection, parse_template_file, parse_template_bytes
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
    unmapped_sections: List[str]          # 양식에는 있으나 외부 문서에 내용 없는 섹션 heading
    output_docx_bytes: bytes
    output_md: str


def transform_document(
    external_data: bytes,
    external_suffix: str,
    template_data: bytes,
    template_suffix: str,
    include_source_note: bool = False,
    llm=None,
) -> TransformResult:
    """
    외부 문서 + 우리 양식 → TransformResult.
    llm: 로드된 LLM 객체(있으면 사용, 없으면 휴리스틱 폴백).
    """
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
            "content": f"_(원본 문서에서 추출됨)_",
            "mapped": True,
        })

    output_docx = render_docx_bytes(sections_dicts)
    output_md = render_md_text(sections_dicts)

    return TransformResult(
        confidence=confidence,
        mapped_sections=mapped,
        unmapped_sections=unmapped,
        output_docx_bytes=output_docx,
        output_md=output_md,
    )


def _map_heuristic(
    external_text: str,
    template_sections: List[TemplateSection],
) -> List[MappedSection]:
    """키워드 유사도 기반 단순 매핑 (LLM 없을 때 폴백)."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", external_text) if p.strip()]

    result: List[MappedSection] = []
    used: set[int] = set()

    for sec in template_sections:
        keywords = _extract_keywords(sec.heading)
        best_idx: Optional[int] = None
        best_score = 0.0

        for idx, para in enumerate(paragraphs):
            if idx in used:
                continue
            score = _keyword_overlap(keywords, para)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is not None and best_score > 0.0:
            used.add(best_idx)
            result.append(MappedSection(
                heading=sec.heading,
                level=sec.level,
                content=paragraphs[best_idx],
                mapped=True,
            ))
        else:
            # 매핑 못찾으면 남은 단락에서 순서대로 채움
            remaining = [paragraphs[i] for i in range(len(paragraphs)) if i not in used]
            if remaining:
                used.add(next(i for i in range(len(paragraphs)) if i not in used and paragraphs[i] == remaining[0]))
                result.append(MappedSection(
                    heading=sec.heading,
                    level=sec.level,
                    content=remaining[0],
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


def _map_with_llm(
    external_text: str,
    template_sections: List[TemplateSection],
    llm,
) -> List[MappedSection]:
    """LLM 기반 매핑 (실제 LLM 사용 시)."""
    section_headings = "\n".join(
        f"{i+1}. {s.heading}" for i, s in enumerate(template_sections)
    )
    prompt = (
        f"다음 외부 문서를 우리 양식의 각 섹션에 맞게 재구성하세요.\n\n"
        f"[우리 양식 섹션 목록]\n{section_headings}\n\n"
        f"[외부 문서 내용]\n{external_text[:3000]}\n\n"
        f"각 섹션 번호와 해당 내용을 JSON 형식으로 출력하세요: "
        f"[{{\"section\": 1, \"content\": \"...\"}}]"
    )
    try:
        response = llm.generate(prompt, max_tokens=2000)
        import json, re as _re
        m = _re.search(r"\[.*\]", response, _re.DOTALL)
        if not m:
            return _map_heuristic(external_text, template_sections)
        items = json.loads(m.group())
        content_map = {item["section"]: item.get("content", "") for item in items if isinstance(item, dict)}
        result = []
        for i, sec in enumerate(template_sections, start=1):
            content = content_map.get(i, "")
            result.append(MappedSection(
                heading=sec.heading,
                level=sec.level,
                content=content,
                mapped=bool(content),
            ))
        return result
    except Exception:
        return _map_heuristic(external_text, template_sections)


def _extract_keywords(heading: str) -> set[str]:
    stop = {"및", "의", "와", "과", "을", "를", "이", "가", "에", "도", "로", "은", "는"}
    tokens = re.findall(r"[가-힣a-zA-Z]+", heading)
    return {t.lower() for t in tokens if t not in stop and len(t) >= 2}


def _keyword_overlap(keywords: set[str], text: str) -> float:
    if not keywords:
        return 0.0
    text_lower = text.lower()
    matched = sum(1 for kw in keywords if kw in text_lower)
    return matched / len(keywords)
