from __future__ import annotations

from typing import Any, Mapping, Sequence


def _coerce_file_texts(file_texts: Sequence[str] | None) -> list[str]:
    return [str(text) for text in (file_texts or []) if str(text).strip()]


def _joined_file_texts(file_texts: Sequence[str]) -> str:
    return "\n\n---\n".join(file_texts)


def _card_04_documents(
    card: Mapping[str, Any],
    query: str,
    file_texts: Sequence[str],
) -> tuple[str, list[str]]:
    if _card_id(card) == "card_04_document_review" and file_texts and not query.strip():
        return file_texts[0], list(file_texts[1:])
    return query, list(file_texts)


def _build_context(card: Mapping[str, Any], query: str, file_texts: Sequence[str]) -> dict[str, Any]:
    first_file = file_texts[0] if file_texts else ""
    draft_document, reference_documents = _card_04_documents(card, query, file_texts)

    return {
        "query": query,
        # Card 1
        "message_text": query,
        "sender_context": "",
        # Card 2
        "external_document": query,
        "our_template": first_file,
        "document_type": "",
        # Card 3
        "past_documents": list(file_texts),
        "new_situation": query,
        "draft_type": "",
        "length_guide": "",
        # Card 4
        "draft_document": draft_document,
        "review_criteria": [],
        "reference_documents": reference_documents,
        # Card 5
        "transaction_text": query,
        "account_code_map": {},
        "currency": "KRW",
        # Card 6
        "blank_form": query,
        "our_data": {"첨부자료": _joined_file_texts(file_texts)} if file_texts else {},
        "form_type": "",
        "strict_mode": True,
    }


def _card_id(card: Mapping[str, Any]) -> str:
    return str(card.get("card_id") or "").lower()


def _manual_fallback_render(
    tmpl: str,
    card: Mapping[str, Any],
    *,
    query: str,
    file_texts: Sequence[str],
) -> str:
    card_id = _card_id(card)

    if card_id == "card_01_request_parse" or "message_text" in tmpl:
        return "\n".join([
            "## 분석 대상 메시지",
            query,
            "",
            "위 메시지를 분석하여 JSON 형식으로 출력하십시오.",
        ]).strip()

    if card_id == "card_02_external_to_our_format" or "external_document" in tmpl:
        return "\n".join([
            "## 외부 문서",
            query,
            "",
            "## 우리 회사 보고서 양식",
            file_texts[0] if file_texts else "",
            "",
            "위 외부 문서를 우리 양식에 맞게 변환하여 JSON으로 출력하십시오.",
        ]).strip()

    if card_id == "card_03_new_draft_from_past" or "past_documents" in tmpl:
        parts = ["## 새 상황·요구사항", query, "", "## 참고 과거 문서"]
        for idx, text in enumerate(file_texts, start=1):
            parts.extend([f"### 과거 문서 {idx}", text])
        parts.append("위 정보를 바탕으로 새 초안을 JSON 형식으로 출력하십시오.")
        return "\n".join(parts).strip()

    if card_id == "card_04_document_review" or "draft_document" in tmpl or "reference_documents" in tmpl:
        draft_document, reference_documents = _card_04_documents(card, query, file_texts)
        parts = ["## 검토 대상 문서", draft_document]
        if reference_documents:
            parts.extend(["", "## 참고 문서"])
            for idx, text in enumerate(reference_documents, start=1):
                parts.extend([f"### 참고 {idx}", text])
        parts.append("위 문서를 검토하여 JSON 형식으로 출력하십시오.")
        return "\n".join(parts).strip()

    if card_id == "card_05_bank_to_accounting" or "transaction_text" in tmpl:
        return "\n".join([
            "## 거래내역",
            query,
            "",
            "통화: KRW",
            "",
            "위 거래내역을 분류하여 JSON 형식으로 출력하십시오.",
        ]).strip()

    if card_id == "card_06_fill_external_form" or "blank_form" in tmpl:
        parts = [
            "## 빈 외부 양식",
            query,
            "",
            "## 우리 회사 보유 데이터",
            _joined_file_texts(file_texts),
            "",
            "strict_mode: True",
            "",
            "위 양식에 우리 데이터를 채워 JSON 형식으로 출력하십시오.",
        ]
        return "\n".join(parts).strip()

    rendered = tmpl.replace("{{ query }}", query)
    if rendered == tmpl and ("{{" in tmpl or "{%" in tmpl):
        rendered = "\n".join(["## 요청", query])
    if file_texts:
        rendered += "\n\n## 첨부 파일 내용\n" + _joined_file_texts(file_texts)
    return rendered.strip()


def _has_template_literal(text: str) -> bool:
    return "{{" in text or "{%" in text or "%}" in text


def _template_consumes_file_texts(tmpl: str, card: Mapping[str, Any]) -> bool:
    card_id = _card_id(card)
    if card_id in {
        "card_02_external_to_our_format",
        "card_03_new_draft_from_past",
        "card_04_document_review",
        "card_06_fill_external_form",
    }:
        return True
    return any(
        marker in tmpl
        for marker in (
            "our_template",
            "past_documents",
            "reference_documents",
            "our_data",
        )
    )


def render_card_user_prompt(
    card: Mapping[str, Any],
    *,
    query: str | None,
    file_texts: Sequence[str] | None,
) -> str:
    tmpl = str(card.get("user_prompt_template") or "{{ query }}")
    query_text = query or ""
    file_text_list = _coerce_file_texts(file_texts)
    context = _build_context(card, query_text, file_text_list)

    try:
        from jinja2 import StrictUndefined
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}
        rendered = env.from_string(tmpl).render(**context).strip()
    except Exception:
        rendered = _manual_fallback_render(
            tmpl,
            card,
            query=query_text,
            file_texts=file_text_list,
        )

    if _has_template_literal(rendered):
        rendered = _manual_fallback_render(
            tmpl,
            card,
            query=query_text,
            file_texts=file_text_list,
        )

    if (
        file_text_list
        and not _template_consumes_file_texts(tmpl, card)
        and "## 첨부 파일 내용" not in rendered
    ):
        rendered += "\n\n## 첨부 파일 내용\n" + _joined_file_texts(file_text_list)

    return rendered
