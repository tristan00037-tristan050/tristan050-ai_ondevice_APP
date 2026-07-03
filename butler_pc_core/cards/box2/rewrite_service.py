from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .model_chain import ModelChainStatus, inspect_model_chain

OUTPUT_SECTIONS = [
    "제목",
    "발행일",
    "담당자",
    "핵심 내용",
    "합의사항",
    "금액/일정",
    "확인 필요",
    "최종 문안",
]

EVAL_CANDIDATE_PATHS = [
    Path.home() / "Desktop/도우미폴더/box2b_v5_outputs/rewrite/eval",
    Path.home() / "Desktop/도우미폴더/box2b_v5_outputs/rewrite",
    Path("/Volumes/T7 Shield/학습모델 폴더/알고리즘개발팀/box2b_v5_outputs/rewrite/eval"),
]

CHECK_REQUIRED = "[확인 필요]"
SCORER_VERSION = "box2.eval.v3_gold"
BASELINE_SCORE = 0.30
EXPECTED_GOLD_CASE_COUNT = 10
EXPECTED_EVAL_SHA256_PREFIX = "1e0f2766"
FORBIDDEN_REPORT_KEYS = {
    "foreign",
    "foreign_doc",
    "our_format",
    "input_1",
    "input_2",
    "must_keep",
    "fields",
    "rewritten_doc",
    "raw",
    "raw_text",
}

VENDOR_LABELS = (
    "거래처",
    "거래상대방",
    "협력사",
    "공급자",
    "공급처",
    "업체명",
    "회사명",
    "상호",
    "수신",
    "발신",
    "vendor",
    "client",
)
ITEM_LABELS = ("품목", "제품", "제품명", "항목", "서비스", "내용", "상품명", "물품", "거래품목", "용역명", "item", "product")
QUANTITY_LABELS = ("수량", "개수", "qty", "quantity")
UNIT_PRICE_LABELS = ("단가", "공급단가", "개당", "건당", "unit price", "unit_price", "unitprice")
AMOUNT_LABELS = ("합계", "총액", "총 금액", "청구금액", "금액", "공급가액", "견적금액", "total", "amount")
SCHEDULE_LABELS = ("납품 일정", "납기", "일정", "마감", "기한", "납품일", "due", "deadline")
ALL_VALUE_LABELS = VENDOR_LABELS + ITEM_LABELS + QUANTITY_LABELS + UNIT_PRICE_LABELS + AMOUNT_LABELS + SCHEDULE_LABELS
GENERIC_ITEM_LABELS = {"서비스", "내용"}

COMPANY_NAME_HINTS = (
    "주식회사",
    "(주)",
    "㈜",
    "상사",
    "테크",
    "솔루션",
    "시스템즈",
    "유통",
    "전자",
    "산업",
    "컴퍼니",
    "파트너스",
    "물산",
    "정보통신",
    "글로벌",
)
QUANTITY_UNITS = "개|건|식|대|명|개월|회|박스|세트|EA|ea"
MONEY_PATTERN = r"(?:₩\s*)?\d{1,3}(?:,\d{3})+(?:\s*원)?|\d+(?:\.\d+)?\s*(?:원|만원|억원)"
DATE_PATTERN = r"\d{4}\s*(?:[-./]|년)\s*\d{1,2}\s*(?:[-./]|월)\s*\d{1,2}\s*(?:일)?|\d{1,2}\s*월\s*\d{1,2}\s*일"
_SEPARATOR_RE = re.compile(r"\r?\n|[|;，]|/")
_QUANTITY_VALUE_RE = re.compile(rf"^\d[\d,]*(?:\s*(?:{QUANTITY_UNITS}|석))?$", re.IGNORECASE)
_UNIT_PRICE_VALUE_RE = re.compile(r"^(?:₩\s*)?\d[\d,]*(?:\s*원)?$|^\d+(?:\.\d+)?\s*(?:원|만원|억원)$")
_AMOUNT_VALUE_RE = re.compile(MONEY_PATTERN)


@dataclass(frozen=True)
class RewriteOptions:
    tone: str = "company_standard"
    preserve_numbers: bool = True
    redact_sensitive: bool = True


@dataclass(frozen=True)
class RewriteResult:
    rewritten_doc: str
    confidence: float
    model_chain: list[str]
    external_send_zero: bool
    raw_saved_zero: bool
    request_digest: str
    model_chain_status: dict


@dataclass(frozen=True)
class SourceValueExtraction:
    vendor: str = CHECK_REQUIRED
    item: str = CHECK_REQUIRED
    quantity: str = CHECK_REQUIRED
    unit_price: str = CHECK_REQUIRED
    amount: str = CHECK_REQUIRED
    schedule: str = CHECK_REQUIRED


@dataclass(frozen=True)
class LabeledSpan:
    field_name: str
    label: str
    value: str
    start: int
    end: int


def digest_inputs(foreign_doc: str, our_format: str) -> str:
    payload = f"foreign={hashlib.sha256(foreign_doc.encode('utf-8')).hexdigest()}|format={hashlib.sha256(our_format.encode('utf-8')).hexdigest()}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_value(value: str) -> str:
    value = _normalize_space(value)
    value = value.strip(" :-–—|\t,，")
    return value[:500] if value else CHECK_REQUIRED


def _label_alt(labels: tuple[str, ...]) -> str:
    # Longer labels first keeps compound labels such as "총 금액" intact.
    return "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))


def _label_field_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for field_name, labels in (
        ("vendor", VENDOR_LABELS),
        ("item", ITEM_LABELS),
        ("quantity", QUANTITY_LABELS),
        ("unit_price", UNIT_PRICE_LABELS),
        ("amount", AMOUNT_LABELS),
        ("schedule", SCHEDULE_LABELS),
    ):
        for label in labels:
            index[re.sub(r"[\s_]", "", label).lower()] = field_name
    return index


def _is_numeric_slash_context(window: str, slash_start: int, slash_end: int) -> bool:
    left = window[:slash_start].rstrip()
    right = window[slash_end:].lstrip()
    return bool(left and right and left[-1].isdigit() and right[0].isdigit())


def _find_value_end_separator(window: str) -> re.Match[str] | None:
    for match in _SEPARATOR_RE.finditer(window):
        if match.group() == "/" and _is_numeric_slash_context(window, match.start(), match.end()):
            continue
        return match
    return None


def _iter_labeled_spans(text: str) -> list[LabeledSpan]:
    label_index = _label_field_index()
    label_alt = _label_alt(ALL_VALUE_LABELS)
    label_re = re.compile(
        rf"(?:^|(?<=[\s\n/|;,，]))(?P<label>{label_alt})\s*(?:\([^)]*\))?(?:[:：=\-]\s*|\s+)",
        re.IGNORECASE,
    )
    matches = []
    for match in label_re.finditer(text):
        label = match.group("label")
        if label in GENERIC_ITEM_LABELS:
            prev = match.start() - 1
            while prev >= 0 and text[prev].isspace():
                prev -= 1
            if prev >= 0 and text[prev] not in "\n/|;,，":
                continue
        matches.append(match)
    spans: list[LabeledSpan] = []
    for idx, match in enumerate(matches):
        label = match.group("label")
        value_start = match.end()
        next_label_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        separator = _find_value_end_separator(text[value_start:next_label_start])
        value_end = value_start + separator.start() if separator else next_label_start
        value = _clean_value(text[value_start:value_end])
        if value == CHECK_REQUIRED:
            continue
        normalized_label = re.sub(r"[\s_]", "", label).lower()
        field_name = label_index.get(normalized_label)
        if field_name:
            spans.append(LabeledSpan(field_name, label, value, value_start, value_end))
    return spans


def _pick_labeled_span_value(text: str, labels: tuple[str, ...]) -> str:
    wanted = {
        _label_field_index()[re.sub(r"[\s_]", "", label).lower()]
        for label in labels
        if re.sub(r"[\s_]", "", label).lower() in _label_field_index()
    }
    for span in _iter_labeled_spans(text):
        if span.field_name in wanted:
            return span.value
    return CHECK_REQUIRED


def _trim_labeled_segment(value: str) -> str:
    """Keep one source value from inline key/value runs without inventing facts."""

    segment = value
    for pattern in (r"\s+[\/|·]\s+", r"\t+", r";+"):
        segment = re.split(pattern, segment, maxsplit=1)[0]

    all_labels = _label_alt(ALL_VALUE_LABELS)
    segment = re.split(
        rf"\s*[,，]?\s+(?:{all_labels})\s*(?:\([^)]*\))?\s*(?:[:：=\-]|\s+)",
        segment,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_value(segment)


def _extract_first_number(text: str) -> str:
    match = re.search(r"[0-9][0-9,]*(?:원|만원|억원)?", text)
    return match.group(0) if match else CHECK_REQUIRED


def _line_or_check(text: str, keyword: str) -> str:
    for line in text.splitlines():
        if keyword in line and line.strip():
            return line.strip()[:500]
    return CHECK_REQUIRED


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    span_value = _pick_labeled_span_value(text, labels)
    if span_value != CHECK_REQUIRED:
        return span_value

    label_alt = _label_alt(labels)
    pattern = re.compile(
        rf"(?:^|[\n;|/,，])\s*(?:{label_alt})\s*(?:\([^)]*\))?\s*(?:[:：=\-]|\s+)\s*([^\n;|]+)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        value = _trim_labeled_segment(match.group(1))
        if value != CHECK_REQUIRED:
            return value
    return CHECK_REQUIRED


def _looks_like_company_name(value: str) -> bool:
    cleaned = _clean_value(value)
    if cleaned == CHECK_REQUIRED:
        return False
    if re.search(MONEY_PATTERN, cleaned) or re.search(rf"\d+\s*(?:{QUANTITY_UNITS})", cleaned):
        return False
    return any(hint in cleaned for hint in COMPANY_NAME_HINTS)


def _extract_candidate(patterns: tuple[str, ...], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = _clean_value(match.group(1))
            if value != CHECK_REQUIRED:
                return value
    return CHECK_REQUIRED


def _extract_nonstandard_vendor(text: str) -> str:
    strong_anchor_patterns = (
        r"(?:^|\n)\s*견적서\s*[-:：]\s*([^\n|/;]+)",
        r"(?:^|\n)\s*거래상대방\s*(?:[:：=\-]|\s+)\s*([^\n|/;]+)",
        r"(?:^|\n)\s*협력사\s*(?:[:：=\-]|\s+)\s*([^\n|/;]+)",
    )
    candidate = _extract_candidate(strong_anchor_patterns, text)
    if candidate != CHECK_REQUIRED:
        return candidate

    # "거래명세: <회사>" is a weak vendor anchor because 거래명세 can also describe the item.
    # Use it only when the captured value itself has a company-name signal.
    weak_vendor = _extract_candidate((r"(?:^|\n)\s*거래명세(?:서)?\s*[-:：]\s*([^\n|/;]+)",), text)
    if _looks_like_company_name(weak_vendor):
        return weak_vendor

    sentence_vendor = _extract_candidate(
        (
            r"((?:주식회사|㈜|\(주\))\s*[^\n,;|/]{1,40}?)(?:에서|로부터|에게)",
            r"([^\n,;|/]{2,40}?(?:상사|테크|솔루션|시스템즈|유통|전자|산업|컴퍼니|파트너스|물산|정보통신|글로벌))(?:에서|로부터|에게)",
        ),
        text,
    )
    if _looks_like_company_name(sentence_vendor):
        return sentence_vendor
    return CHECK_REQUIRED


def _extract_nonstandard_item(text: str) -> str:
    item_from_trade_detail = _extract_candidate((r"(?:^|\n)\s*거래명세(?:서)?\s*[-:：]\s*([^\n|/;]+)",), text)
    if item_from_trade_detail != CHECK_REQUIRED and not _looks_like_company_name(item_from_trade_detail):
        return item_from_trade_detail

    slash_segments = [segment.strip() for segment in re.split(r"\s+/\s+", text) if segment.strip()]
    if len(slash_segments) >= 2:
        first = slash_segments[0]
        if re.search(r"(?:견적서|거래명세(?:서)?)\s*[-:：]", first):
            candidate = _clean_value(slash_segments[1])
            if candidate != CHECK_REQUIRED and not _looks_like_company_name(candidate):
                return candidate

    sentence_item = _extract_candidate(
        (
            rf"(?:에서|로부터)\s*([^\n,;|/]{{2,80}}?)\s+\d[\d,]*\s*(?:{QUANTITY_UNITS})",
            rf"(?:납품|구매|발주|견적)\s*대상\s*[:：=\-]?\s*([^\n,;|/]{{2,80}}?)\s+\d[\d,]*\s*(?:{QUANTITY_UNITS})",
        ),
        text,
    )
    return sentence_item


def _extract_quantity_value(text: str) -> str:
    labeled = _extract_labeled_value(text, QUANTITY_LABELS)
    if labeled != CHECK_REQUIRED:
        return labeled
    match = re.search(rf"\d[\d,]*\s*(?:{QUANTITY_UNITS})", text)
    return _clean_value(match.group(0)) if match else CHECK_REQUIRED


def _extract_unit_price_value(text: str) -> str:
    labeled = _extract_labeled_value(text, UNIT_PRICE_LABELS)
    money = _extract_money_value(labeled)
    if money != CHECK_REQUIRED:
        return money
    if labeled != CHECK_REQUIRED:
        return labeled
    match = re.search(rf"(?:단가|공급단가|개당|건당)\s*(?:[:：=\-]|\s+)?\s*({MONEY_PATTERN})", text)
    return _clean_value(match.group(1)) if match else CHECK_REQUIRED


def _normalize_money_for_compare(value: str) -> str:
    if value == CHECK_REQUIRED:
        return ""
    return re.sub(r"[₩,\s원]", "", str(value)).strip()


def _money_has_amount_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 24): min(len(text), end + 24)]
    amount_context = r"합계|총액|총\s*금액|청구금액|견적금액|공급가액|금액|부가세\s*포함|연\s*|월\s*"
    has_amount_context = bool(re.search(amount_context, window, flags=re.IGNORECASE))
    if re.search(_label_alt(UNIT_PRICE_LABELS), window, flags=re.IGNORECASE) and not has_amount_context:
        return False
    return has_amount_context


def _extract_amount(text: str, *, unit_price: str = CHECK_REQUIRED) -> str:
    labeled = _extract_labeled_value(text, AMOUNT_LABELS)
    if labeled != CHECK_REQUIRED:
        money = _extract_money_value(labeled)
        return money if money != CHECK_REQUIRED else labeled

    unit_norm = _normalize_money_for_compare(unit_price)
    candidates = []
    for match in re.finditer(MONEY_PATTERN, text):
        money = _clean_value(match.group(0))
        if unit_norm and _normalize_money_for_compare(money) == unit_norm:
            continue
        if _money_has_amount_context(text, match.start(), match.end()):
            candidates.append(money)
    return candidates[-1] if candidates else CHECK_REQUIRED


def _extract_money_value(text: str) -> str:
    match = re.search(MONEY_PATTERN, text)
    return _clean_value(match.group(0)) if match else CHECK_REQUIRED


def _extract_schedule(text: str) -> str:
    labeled = _extract_labeled_value(text, SCHEDULE_LABELS)
    if labeled != CHECK_REQUIRED:
        return labeled
    date_match = re.search(DATE_PATTERN, text)
    if date_match and not _date_has_schedule_context(text, date_match.start(), date_match.end()):
        return CHECK_REQUIRED
    return _clean_value(date_match.group(0)) if date_match else CHECK_REQUIRED


def _date_has_schedule_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 24): min(len(text), end + 24)]
    return bool(re.search(_label_alt(SCHEDULE_LABELS), window, flags=re.IGNORECASE)) or bool(
        re.search(r"납품|마감|기한|까지", window)
    )


def _table_cells(line: str) -> list[str]:
    if "|" in line:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]
    if "\t" in line:
        return [cell.strip() for cell in line.split("\t")]
    return []


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells)


def _field_from_header(header: str) -> str | None:
    normalized = re.sub(r"[\s_()/]", "", header).lower()
    label_map = [
        ("vendor", VENDOR_LABELS),
        ("item", ITEM_LABELS),
        ("quantity", QUANTITY_LABELS),
        ("unit_price", UNIT_PRICE_LABELS),
        ("amount", AMOUNT_LABELS),
        ("schedule", SCHEDULE_LABELS),
    ]
    for field_name, labels in label_map:
        for label in labels:
            label_norm = re.sub(r"[\s_()/]", "", label).lower()
            if label_norm and label_norm in normalized:
                return field_name
    return None


def _extract_table_values(text: str) -> SourceValueExtraction:
    rows = [_table_cells(line) for line in text.splitlines()]
    rows = [row for row in rows if row and not _is_table_separator(row)]

    for header, values in zip(rows, rows[1:]):
        if len(values) < 2:
            continue

        extracted: dict[str, str] = {}
        for idx, header_cell in enumerate(header):
            field_name = _field_from_header(header_cell)
            if not field_name or idx >= len(values):
                continue
            value = _clean_value(values[idx])
            if value != CHECK_REQUIRED:
                extracted[field_name] = value

        if len(extracted) >= 2:
            unit_price = extracted.get("unit_price", CHECK_REQUIRED)
            unit_money = _extract_money_value(unit_price)
            if unit_money != CHECK_REQUIRED:
                unit_price = unit_money

            amount = extracted.get("amount", CHECK_REQUIRED)
            amount_money = _extract_money_value(amount)
            if amount_money != CHECK_REQUIRED:
                amount = amount_money

            return SourceValueExtraction(
                vendor=extracted.get("vendor", CHECK_REQUIRED),
                item=extracted.get("item", CHECK_REQUIRED),
                quantity=extracted.get("quantity", CHECK_REQUIRED),
                unit_price=unit_price,
                amount=amount,
                schedule=extracted.get("schedule", CHECK_REQUIRED),
            )

    return SourceValueExtraction()


def _prefer_extracted(primary: str, fallback: str) -> str:
    return primary if primary != CHECK_REQUIRED else fallback


def _extract_structured_values(foreign_doc: str) -> SourceValueExtraction:
    table_values = _extract_table_values(foreign_doc)

    vendor = _prefer_extracted(
        _extract_labeled_value(foreign_doc, VENDOR_LABELS),
        _extract_nonstandard_vendor(foreign_doc),
    )
    item = _prefer_extracted(
        _extract_labeled_value(foreign_doc, ITEM_LABELS),
        _extract_nonstandard_item(foreign_doc),
    )
    quantity = _extract_quantity_value(foreign_doc)
    unit_price = _extract_unit_price_value(foreign_doc)
    item, quantity = _split_item_tail_quantity(item, quantity)

    final_unit_price = _prefer_extracted(unit_price, table_values.unit_price)

    values = SourceValueExtraction(
        vendor=_prefer_extracted(vendor, table_values.vendor),
        item=_prefer_extracted(item, table_values.item),
        quantity=_prefer_extracted(quantity, table_values.quantity),
        unit_price=final_unit_price,
        amount=_prefer_extracted(_extract_amount(foreign_doc, unit_price=final_unit_price), table_values.amount),
        schedule=_prefer_extracted(_extract_schedule(foreign_doc), table_values.schedule),
    )
    return _validate_source_spans(foreign_doc, values)


def _split_item_tail_quantity(item: str, quantity: str) -> tuple[str, str]:
    if item == CHECK_REQUIRED:
        return item, quantity
    match = re.fullmatch(rf"(.+?)\s+(\d[\d,]*\s*(?:{QUANTITY_UNITS}|석))", item, flags=re.IGNORECASE)
    if not match:
        return item, quantity
    item_head = _clean_value(match.group(1))
    tail_quantity = _clean_value(match.group(2))
    if item_head == CHECK_REQUIRED or re.search(MONEY_PATTERN, tail_quantity):
        return item, quantity
    return item_head, tail_quantity if quantity == CHECK_REQUIRED else quantity


def _source_span_exists(raw_text: str, value: str) -> bool:
    if value == CHECK_REQUIRED:
        return True
    return _normalize_space(value) in _normalize_space(raw_text)


def _is_date_like(value: str) -> bool:
    cleaned = value.strip()
    return bool(re.fullmatch(DATE_PATTERN, cleaned)) or bool(re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", cleaned))


def _field_semantic_valid(field_name: str, value: str) -> bool:
    if value == CHECK_REQUIRED:
        return True
    cleaned = _clean_value(value)
    if cleaned == CHECK_REQUIRED:
        return False
    if field_name == "quantity":
        return not _is_date_like(cleaned) and bool(_QUANTITY_VALUE_RE.fullmatch(cleaned))
    if field_name == "unit_price":
        return not _is_date_like(cleaned) and bool(_UNIT_PRICE_VALUE_RE.fullmatch(cleaned))
    if field_name == "amount":
        return not _is_date_like(cleaned) and bool(_AMOUNT_VALUE_RE.fullmatch(cleaned))
    if field_name == "schedule":
        return bool(re.search(DATE_PATTERN, cleaned))
    return True


def _validate_source_spans(raw_text: str, values: SourceValueExtraction) -> SourceValueExtraction:
    cleaned: dict[str, str] = {}
    for field_name in ("vendor", "item", "quantity", "unit_price", "amount", "schedule"):
        value = getattr(values, field_name)
        if _source_span_exists(raw_text, value) and _field_semantic_valid(field_name, value):
            cleaned[field_name] = value
        else:
            cleaned[field_name] = CHECK_REQUIRED
    return SourceValueExtraction(**cleaned)


def _format_key_values(values: SourceValueExtraction) -> str:
    return (
        f"거래처={values.vendor}; 품목={values.item}; 수량={values.quantity}; "
        f"단가={values.unit_price}; 금액={values.amount}; 일정={values.schedule}"
    )


def _missing_fields(values: SourceValueExtraction) -> list[str]:
    missing = []
    for field_name, label in [
        ("vendor", "거래처"),
        ("item", "품목"),
        ("quantity", "수량"),
        ("unit_price", "단가"),
        ("amount", "금액"),
        ("schedule", "일정"),
    ]:
        if getattr(values, field_name) == CHECK_REQUIRED:
            missing.append(label)
    return missing


def rewrite_to_company_format(foreign_doc: str, our_format: str, options: RewriteOptions | None = None, status: ModelChainStatus | None = None) -> RewriteResult:
    opts = options or RewriteOptions()
    chain_status = status or inspect_model_chain()
    request_digest = digest_inputs(foreign_doc, our_format)

    title = _line_or_check(foreign_doc, "제목")
    issue_date = _line_or_check(foreign_doc, "발행")
    owner = _line_or_check(foreign_doc, "담당")
    agreement = _line_or_check(foreign_doc, "합의")
    values = _extract_structured_values(foreign_doc)
    missing = _missing_fields(values)
    missing_text = ", ".join(missing) if missing else "없음"

    rewritten = "\n".join([
        f"제목: {title}",
        f"발행일: {issue_date}",
        f"담당자: {owner}",
        f"핵심 내용: 원문 확인값을 보존하여 전사했습니다. {_format_key_values(values)}",
        f"합의사항: {agreement}",
        f"금액/일정: 금액 {values.amount} / 일정 {values.schedule}",
        f"확인 필요: 원문에 명확히 없는 항목은 [확인 필요]로 남겼습니다. 누락={missing_text}",
        "최종 문안: 존재하지 않는 금액, 날짜, 담당자, 계약 조건은 새로 만들지 않습니다.",
    ])

    confidence = 0.72 if chain_status.load_mode == "contract_only" else 0.86
    if not opts.preserve_numbers:
        confidence -= 0.05
    if not opts.redact_sensitive:
        confidence -= 0.05
    if missing:
        confidence -= min(0.18, len(missing) * 0.03)

    return RewriteResult(
        rewritten_doc=rewritten,
        confidence=max(0.0, min(1.0, confidence)),
        model_chain=["base", "butler_v3", "helper_3"],
        external_send_zero=True,
        raw_saved_zero=True,
        request_digest=request_digest,
        model_chain_status=asdict(chain_status),
    )


def _canon_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[,，₩￦]", "", normalized)
    normalized = re.sub(r"(?:KRW|원)", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(rf"(?<=\d)(?:{QUANTITY_UNITS}|석)\b", "", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def _format_label_set(format_value: Any, candidate_labels: set[str]) -> set[str]:
    if isinstance(format_value, Mapping):
        return {str(label) for label in format_value if str(label) in candidate_labels}
    if isinstance(format_value, list):
        return {str(label) for label in format_value if str(label) in candidate_labels}

    format_text = str(format_value)
    return {label for label in candidate_labels if re.search(rf"(?<!\w){re.escape(label)}(?!\w)", format_text)}


def _allowed_gold_labels(fields: Mapping[str, str], format_value: Any) -> list[str]:
    field_labels = {str(label).strip() for label in fields if str(label).strip()}
    format_labels = _format_label_set(format_value, field_labels)
    return sorted(field_labels & format_labels, key=len, reverse=True)


def _parse_allowed_label_values(rewritten_doc: str, allowed_labels: list[str]) -> dict[str, str]:
    if not allowed_labels:
        return {}

    label_alt = "|".join(re.escape(label) for label in sorted(allowed_labels, key=len, reverse=True))
    label_re = re.compile(
        rf"(?:^|(?<=[\s\n/|;]))(?P<label>{label_alt})\s*(?:[:：=]\s*)",
        flags=re.IGNORECASE,
    )
    matches = list(label_re.finditer(rewritten_doc))
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group("label")
        value_start = match.end()
        next_label_start = matches[index + 1].start() if index + 1 < len(matches) else len(rewritten_doc)
        segment = rewritten_doc[value_start:next_label_start]
        stop_match = re.search(r"\n|/|\||;", segment)
        value_end = value_start + stop_match.start() if stop_match else next_label_start
        value = _clean_value(rewritten_doc[value_start:value_end])
        if value and value != CHECK_REQUIRED and label not in values:
            values[label] = value
    return values


def score_rewrite_against_gold(
    rewritten_doc: str,
    *,
    must_keep: list[str],
    fields: Mapping[str, str],
    format_value: Any,
) -> dict[str, float | int]:
    allowed_labels = _allowed_gold_labels(fields, format_value)
    observed = _parse_allowed_label_values(rewritten_doc, allowed_labels)
    canon_doc = _canon_value(rewritten_doc)
    keep_values = [value for value in must_keep if isinstance(value, str) and value]

    exact_hits = sum(1 for value in keep_values if value in rewritten_doc)
    canonical_hits = sum(1 for value in keep_values if _canon_value(value) and _canon_value(value) in canon_doc)

    true_positive = 0
    false_positive = 0
    false_negative = 0
    exact_field_hits = 0
    for label in allowed_labels:
        gold_value = str(fields[label])
        observed_value = observed.get(label, "")
        if not observed_value or observed_value == CHECK_REQUIRED:
            false_negative += 1
            continue
        if _canon_value(observed_value) == _canon_value(gold_value):
            true_positive += 1
            if observed_value == gold_value:
                exact_field_hits += 1
        else:
            false_positive += 1
            false_negative += 1

    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    keep_denominator = len(keep_values) or 1

    return {
        "value_exact_preservation": exact_hits / keep_denominator,
        "value_canonical_preservation": canonical_hits / keep_denominator,
        "field_precision": 1.0 if precision_denominator == 0 else true_positive / precision_denominator,
        "field_recall": 1.0 if recall_denominator == 0 else true_positive / recall_denominator,
        "false_positive_total": false_positive,
        "false_negative_total": false_negative,
        "field_exact_hits": exact_field_hits,
        "field_total": len(allowed_labels),
    }


def evaluate_rewrite_contract(
    rewritten_doc: str,
    foreign_doc: str,
    our_format: Any,
    *,
    must_keep: list[str] | None = None,
    fields: Mapping[str, str] | None = None,
) -> dict[str, float | bool | int | str]:
    gold_values = must_keep or []
    gold_fields = fields or {}
    gold_score = score_rewrite_against_gold(
        rewritten_doc,
        must_keep=gold_values,
        fields=gold_fields,
        format_value=our_format,
    )
    section_hits = sum(1 for section in OUTPUT_SECTIONS if f"{section}:" in rewritten_doc)
    return {
        "schema_version": SCORER_VERSION,
        "scorer_version": SCORER_VERSION,
        "eval_set_path": "contract_inline",
        "sample_count": 1,
        "rewrite_structure_accuracy": section_hits / len(OUTPUT_SECTIONS),
        "required_field_coverage": gold_score["field_recall"],
        "unsupported_fact_rate": float(gold_score["false_positive_total"]),
        "format_match_score": 1.0 if "최종 문안:" in rewritten_doc else 0.0,
        "semantic_preservation_score": gold_score["value_canonical_preservation"],
        "value_exact_preservation": gold_score["value_exact_preservation"],
        "value_canonical_preservation": gold_score["value_canonical_preservation"],
        "field_precision": gold_score["field_precision"],
        "field_recall": gold_score["field_recall"],
        "false_positive_total": gold_score["false_positive_total"],
        "false_negative_total": gold_score["false_negative_total"],
        "mock_result": False,
        "external_send_zero": True,
        "raw_saved_zero": True,
    }


def find_eval_set(candidate_paths: list[Path] | None = None) -> Path | None:
    for candidate in candidate_paths or EVAL_CANDIDATE_PATHS:
        if candidate.exists():
            if candidate.is_file() and candidate.suffix.lower() in {".json", ".jsonl"}:
                return candidate
            if candidate.is_dir():
                files = sorted(
                    child for child in candidate.rglob("*")
                    if child.is_file() and child.suffix.lower() in {".json", ".jsonl"}
                )
                if files:
                    return candidate
    return None


def _load_eval_samples(eval_path: Path) -> list[dict[str, Any]]:
    files = [eval_path] if eval_path.is_file() else sorted(
        child for child in eval_path.rglob("*") if child.is_file() and child.suffix.lower() in {".json", ".jsonl"}
    )
    samples: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonl":
            for line in text.splitlines():
                if line.strip():
                    item = json.loads(line)
                    if isinstance(item, dict):
                        samples.append(item)
        else:
            data = json.loads(text)
            if isinstance(data, list):
                samples.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                rows = data.get("samples") or data.get("items") or []
                if isinstance(rows, list):
                    samples.extend(item for item in rows if isinstance(item, dict))
    return samples


def _eval_set_sha256(eval_path: Path) -> str:
    hasher = hashlib.sha256()
    files = [eval_path] if eval_path.is_file() else sorted(
        child for child in eval_path.rglob("*") if child.is_file() and child.suffix.lower() in {".json", ".jsonl"}
    )
    for path in files:
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _validate_case_schema(item: Mapping[str, Any], *, index: int) -> tuple[str | None, tuple[str, Any, list[str], dict[str, str]] | None]:
    legacy_keys = {"foreign_doc", "our_format", "input_1", "input_2"}
    if legacy_keys.intersection(item):
        return f"CASE_{index}_LEGACY_KEYS_FORBIDDEN", None

    foreign = item.get("foreign")
    if not isinstance(foreign, str) or not foreign.strip():
        return f"CASE_{index}_FOREIGN_MISSING", None

    format_value = item.get("format")
    if format_value is None:
        return f"CASE_{index}_FORMAT_MISSING", None

    must_keep_raw = item.get("must_keep")
    if (
        not isinstance(must_keep_raw, list)
        or not must_keep_raw
        or any(not isinstance(value, str) or not value for value in must_keep_raw)
    ):
        return f"CASE_{index}_MUST_KEEP_INVALID", None

    fields_raw = item.get("fields")
    if (
        not isinstance(fields_raw, Mapping)
        or not fields_raw
        or any(not isinstance(label, str) or not isinstance(value, str) or not label or not value for label, value in fields_raw.items())
    ):
        return f"CASE_{index}_FIELDS_INVALID", None

    fields = {str(label): str(value) for label, value in fields_raw.items()}
    if not _allowed_gold_labels(fields, format_value):
        return f"CASE_{index}_ALLOWED_LABELS_EMPTY", None

    return None, (foreign, format_value, list(must_keep_raw), fields)


def _assert_digest_safe_report(report: Mapping[str, Any]) -> None:
    if FORBIDDEN_REPORT_KEYS.intersection(report):
        raise ValueError("REPORT_FORBIDDEN_KEY")


def _empty_eval(status: str, eval_path: str = "", eval_set_sha256: str = "") -> dict[str, float | bool | int | str]:
    report = {
        "schema_version": SCORER_VERSION,
        "scorer_version": SCORER_VERSION,
        "status": status,
        "eval_set_path": eval_path,
        "eval_set_sha256": eval_set_sha256,
        "baseline_score": BASELINE_SCORE,
        "new_score": 0.0,
        "value_exact_preservation": 0.0,
        "value_canonical_preservation": 0.0,
        "delta": -BASELINE_SCORE,
        "n": 0,
        "sample_count": 0,
        "field_precision": 0.0,
        "field_recall": 0.0,
        "false_positive_total": 0,
        "false_negative_total": 0,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "mock_result": False,
    }
    _assert_digest_safe_report(report)
    return report


def _aggregate_scores(
    *,
    selected: Path,
    eval_set_sha256: str,
    scores: list[dict[str, float | bool | int | str]],
) -> dict[str, float | bool | int | str]:
    sample_count = len(scores)
    avg = lambda key: sum(float(row[key]) for row in scores) / sample_count
    false_positive_total = sum(int(row["false_positive_total"]) for row in scores)
    false_negative_total = sum(int(row["false_negative_total"]) for row in scores)
    canonical_score = avg("value_canonical_preservation")
    exact_score = avg("value_exact_preservation")
    status = "PASS" if sample_count == EXPECTED_GOLD_CASE_COUNT else "PARTIAL"
    if not eval_set_sha256.startswith(EXPECTED_EVAL_SHA256_PREFIX):
        status = "PARTIAL_EVAL_SHA_MISMATCH"

    report = {
        "schema_version": SCORER_VERSION,
        "scorer_version": SCORER_VERSION,
        "status": status,
        "eval_set_path": str(selected),
        "eval_set_sha256": eval_set_sha256,
        "baseline_score": BASELINE_SCORE,
        "new_score": canonical_score,
        "value_exact_preservation": exact_score,
        "value_canonical_preservation": canonical_score,
        "delta": canonical_score - BASELINE_SCORE,
        "n": sample_count,
        "sample_count": sample_count,
        "field_precision": avg("field_precision"),
        "field_recall": avg("field_recall"),
        "false_positive_total": false_positive_total,
        "false_negative_total": false_negative_total,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "mock_result": False,
    }
    _assert_digest_safe_report(report)
    return report


def evaluate_eval_set(eval_path: Path | None = None) -> dict[str, float | bool | int | str]:
    selected = eval_path or find_eval_set()
    if selected is None:
        return _empty_eval("BLOCK_EVAL_SET_MISSING")

    samples = _load_eval_samples(selected)
    if not samples:
        return _empty_eval("BLOCK_EVAL_SET_MISSING", str(selected), _eval_set_sha256(selected))

    eval_set_sha256 = _eval_set_sha256(selected)
    scores: list[dict[str, float | bool | int | str]] = []
    for index, item in enumerate(samples, start=1):
        code, validated = _validate_case_schema(item, index=index)
        if code is not None or validated is None:
            return _empty_eval(code or "SCHEMA_INVALID", str(selected), eval_set_sha256)
        foreign_doc, format_value, must_keep, fields = validated
        result = rewrite_to_company_format(foreign_doc, str(format_value))
        scores.append(
            evaluate_rewrite_contract(
                result.rewritten_doc,
                foreign_doc,
                format_value,
                must_keep=must_keep,
                fields=fields,
            )
        )

    return _aggregate_scores(selected=selected, eval_set_sha256=eval_set_sha256, scores=scores)


def write_value_preservation_eval_summary(
    evidence_path: Path = Path("evidence/box2/value_preservation_eval_summary.json"),
    eval_path: Path | None = None,
) -> dict[str, float | bool | int | str]:
    payload = evaluate_eval_set(eval_path)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
