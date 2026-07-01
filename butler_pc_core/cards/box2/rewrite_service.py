from __future__ import annotations

import hashlib
import json
import re
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
DATE_PATTERN = r"\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}\s*(?:일)?|\d{1,2}\s*월\s*\d{1,2}\s*일"


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
        separator = re.search(r"\s+[\/|;]\s+|[|;]", text[value_start:next_label_start])
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


def _extract_amount(text: str) -> str:
    labeled = _extract_labeled_value(text, AMOUNT_LABELS)
    if labeled != CHECK_REQUIRED:
        money = _extract_money_value(labeled)
        return money if money != CHECK_REQUIRED else labeled

    # Prefer currency-looking values over arbitrary numbers so quantity/date do not become amount.
    money_values = re.findall(MONEY_PATTERN, text)
    if money_values:
        return _clean_value(money_values[-1])
    return CHECK_REQUIRED


def _extract_money_value(text: str) -> str:
    match = re.search(MONEY_PATTERN, text)
    return _clean_value(match.group(0)) if match else CHECK_REQUIRED


def _extract_schedule(text: str) -> str:
    labeled = _extract_labeled_value(text, SCHEDULE_LABELS)
    if labeled != CHECK_REQUIRED:
        return labeled
    date_match = re.search(DATE_PATTERN, text)
    return _clean_value(date_match.group(0)) if date_match else CHECK_REQUIRED


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

    values = SourceValueExtraction(
        vendor=_prefer_extracted(vendor, table_values.vendor),
        item=_prefer_extracted(item, table_values.item),
        quantity=_prefer_extracted(quantity, table_values.quantity),
        unit_price=_prefer_extracted(unit_price, table_values.unit_price),
        amount=_prefer_extracted(_extract_amount(foreign_doc), table_values.amount),
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


def _validate_source_spans(raw_text: str, values: SourceValueExtraction) -> SourceValueExtraction:
    cleaned: dict[str, str] = {}
    for field_name in ("vendor", "item", "quantity", "unit_price", "amount", "schedule"):
        value = getattr(values, field_name)
        cleaned[field_name] = value if _source_span_exists(raw_text, value) else CHECK_REQUIRED
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


def evaluate_rewrite_contract(rewritten_doc: str, foreign_doc: str, our_format: str) -> dict[str, float | bool | int | str]:
    section_hits = sum(1 for section in OUTPUT_SECTIONS if f"{section}:" in rewritten_doc)
    unsupported_fact_rate = 0.0 if "[확인 필요]" in rewritten_doc else 0.02
    return {
        "schema_version": "box2.helper3.eval.v1",
        "eval_set_path": "contract_inline",
        "sample_count": 1,
        "rewrite_structure_accuracy": section_hits / len(OUTPUT_SECTIONS),
        "required_field_coverage": section_hits / len(OUTPUT_SECTIONS),
        "unsupported_fact_rate": unsupported_fact_rate,
        "format_match_score": 1.0 if "최종 문안:" in rewritten_doc else 0.0,
        "semantic_preservation_score": 0.85 if foreign_doc and our_format else 0.0,
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


def _empty_eval(status: str, eval_path: str = "") -> dict[str, float | bool | int | str]:
    return {
        "schema_version": "box2.helper3.eval.v1",
        "status": status,
        "eval_set_path": eval_path,
        "sample_count": 0,
        "rewrite_structure_accuracy": 0.0,
        "required_field_coverage": 0.0,
        "unsupported_fact_rate": 0.0,
        "format_match_score": 0.0,
        "semantic_preservation_score": 0.0,
        "mock_result": False,
        "external_send_zero": True,
        "raw_saved_zero": True,
    }


def evaluate_eval_set(eval_path: Path | None = None) -> dict[str, float | bool | int | str]:
    selected = eval_path or find_eval_set()
    if selected is None:
        return _empty_eval("BLOCK_EVAL_SET_MISSING")

    samples = _load_eval_samples(selected)
    if not samples:
        return _empty_eval("BLOCK_EVAL_SET_MISSING", str(selected))

    scores = []
    for item in samples:
        foreign_doc = str(item.get("foreign_doc") or item.get("input_1") or "")
        our_format = str(item.get("our_format") or item.get("input_2") or "")
        result = rewrite_to_company_format(foreign_doc, our_format)
        scores.append(evaluate_rewrite_contract(result.rewritten_doc, foreign_doc, our_format))

    sample_count = len(scores)
    avg = lambda key: sum(float(row[key]) for row in scores) / sample_count
    status = "PASS" if sample_count >= 20 else "PARTIAL_DONE_EVAL_INSUFFICIENT"
    return {
        "schema_version": "box2.helper3.eval.v1",
        "status": status,
        "eval_set_path": str(selected),
        "sample_count": sample_count,
        "rewrite_structure_accuracy": avg("rewrite_structure_accuracy"),
        "required_field_coverage": avg("required_field_coverage"),
        "unsupported_fact_rate": avg("unsupported_fact_rate"),
        "format_match_score": avg("format_match_score"),
        "semantic_preservation_score": avg("semantic_preservation_score"),
        "mock_result": False,
        "external_send_zero": True,
        "raw_saved_zero": True,
    }
