"""Box1 intake router v3.6 attachment feature extraction.

The extractor reads attachment bytes in-process, derives raw-free feature buckets,
and returns only digests, buckets, counts, and fail classes. It must never persist
file names, paths, cell values, document text, OCR text, or transcripts.
"""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Iterable, Sequence

from .persisted_safety import _dlp_scan_all

SCHEMA_VERSION = "attachment_features.v1"
MAX_TEXT_PREVIEW_BYTES = 64 * 1024
MAX_CSV_ROWS = 40
MAX_XLSX_XML_BYTES = 2 * 1024 * 1024

_SHA_PREFIX = "sha256:"

_AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg"}
_SPREADSHEET_EXT = {".csv", ".tsv", ".xlsx", ".xls", ".xlsm"}
_DOC_EXT = {".txt", ".md", ".pdf", ".docx", ".hwp", ".hwpx", ".rtf"}

_ACCOUNTING_HEADERS = {
    "거래일자", "거래일", "일자", "입금", "출금", "잔액", "적요", "내용",
    "상대계좌예금주명", "예금주", "보낸분/받는분", "거래처", "금액", "계정과목",
}
_POLICY_TERMS = ("제1조", "제 1 조", "제2조", "제 2 조", "내규", "규정", "시행일", "준수", "결재", "권한")
_FORMAT_TERMS = ("작성란", "빈칸", "표준 양식", "표준양식", "제출서식", "템플릿", "서식")
_DRAFT_TERMS = ("사업계획", "제안서", "보고서", "계획안", "회의록", "요약", "초안")
_CONVERT_TERMS = ("우리 양식", "외부 문서", "타사 양식", "변환", "서식 맞")


def sha256_bytes(data: bytes) -> str:
    return _SHA_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return _SHA_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(encoded)


def _extension_bucket(filename: str | None) -> str:
    if not filename:
        return "unknown"
    suffix = Path(filename).suffix.casefold()
    if suffix in _AUDIO_EXT:
        return "audio"
    if suffix in _SPREADSHEET_EXT:
        return suffix.lstrip(".")
    if suffix in _DOC_EXT:
        return suffix.lstrip(".")
    return "unknown"


def _mime_bucket(content_type: str | None) -> str:
    if not content_type:
        return "unknown"
    c = content_type.casefold()
    if "spreadsheet" in c or "excel" in c or "csv" in c:
        return "spreadsheet"
    if "pdf" in c:
        return "pdf"
    if "word" in c or "document" in c:
        return "document"
    if c.startswith("audio/"):
        return "audio"
    if c.startswith("text/"):
        return "text"
    return "binary"


def _size_bucket(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "empty"
    if num_bytes < 16_384:
        return "lt16kb"
    if num_bytes < 256_000:
        return "lt256kb"
    if num_bytes < 2_000_000:
        return "lt2mb"
    if num_bytes < 20_000_000:
        return "lt20mb"
    return "gt20mb"


def _decode_preview(data: bytes) -> str:
    sample = data[:MAX_TEXT_PREVIEW_BYTES]
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return sample.decode(encoding)
        except UnicodeDecodeError:
            continue
    return sample.decode("utf-8", errors="ignore")


def _dlp_buckets(text: str) -> list[str]:
    result = _dlp_scan_all(text)
    if result.any_detected:
        return ["DLP_SIGNAL_PRESENT"]
    return []


def _header_digest_set(headers: Iterable[str]) -> list[str]:
    return sorted({sha256_text(" ".join(str(h).casefold().split())) for h in headers if str(h).strip()})


def _column_role_flags(headers: Sequence[str]) -> dict[str, bool]:
    header_text = " ".join(str(h) for h in headers)
    return {
        "has_date_column": any(term in header_text for term in ("거래일", "일자", "날짜", "date")),
        "has_amount_column": any(term in header_text for term in ("입금", "출금", "금액", "amount", "debit", "credit")),
        "has_balance_column": any(term in header_text for term in ("잔액", "balance")),
        "has_counterparty_column": any(term in header_text for term in ("거래처", "상대", "예금주", "받는분", "보내는분")),
    }


def _row_bucket(row_count: int | None) -> str | None:
    if row_count is None:
        return None
    if row_count <= 0:
        return "0"
    if row_count < 10:
        return "lt10"
    if row_count < 100:
        return "lt100"
    if row_count < 1000:
        return "lt1000"
    return "gte1000"


def _spreadsheet_from_csv(text: str) -> tuple[list[str], int]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(StringIO(text), dialect)
    rows: list[list[str]] = []
    for idx, row in enumerate(reader):
        rows.append(row)
        if idx >= MAX_CSV_ROWS:
            break
    if not rows:
        return [], 0
    return [str(item).strip() for item in rows[0]], max(0, len(rows) - 1)


def _xlsx_texts(element: ET.Element) -> str:
    return "".join(text for text in element.itertext()).strip()


def _read_xlsx_xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    info = zf.getinfo(name)
    if info.file_size > MAX_XLSX_XML_BYTES:
        raise RuntimeError("INTAKE_XLSX_XML_TOO_LARGE")
    return ET.fromstring(zf.read(name))


def _load_xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = _read_xlsx_xml(zf, "xl/sharedStrings.xml")
    except KeyError:
        return []
    return [_xlsx_texts(item) for item in root.iter() if item.tag.endswith("}si") or item.tag == "si"]


def _xlsx_column_index(cell_ref: str | None) -> int:
    letters = "".join(ch for ch in str(cell_ref or "") if ch.isalpha()).upper()
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value


def _xlsx_cell_text(cell: ET.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _xlsx_texts(cell)
    value_node = next((child for child in cell if child.tag.endswith("}v") or child.tag == "v"), None)
    if value_node is None or value_node.text is None:
        return ""
    raw_value = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return ""
    return raw_value


def _spreadsheet_from_xlsx(data: bytes) -> tuple[list[str], int, str | None]:
    # Macro workbooks are not accepted by the intake router because their embedded
    # macro surface is irrelevant to destination routing and should be fail-closed.
    # The suffix check is performed by the caller, but encrypted/corrupt zip errors
    # are classified here.
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
            if any(name.casefold().endswith("vbaProject.bin".casefold()) for name in names):
                return [], 0, "INTAKE_MACRO_WORKBOOK_UNSUPPORTED"
            worksheet_names = sorted(name for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if worksheet_names:
                shared_strings = _load_xlsx_shared_strings(zf)
                sheet = _read_xlsx_xml(zf, worksheet_names[0])
                rows = [row for row in sheet.iter() if row.tag.endswith("}row") or row.tag == "row"]
                if not rows:
                    return [], 0, None
                first_cells = [
                    (_xlsx_column_index(cell.attrib.get("r")), _xlsx_cell_text(cell, shared_strings))
                    for cell in rows[0]
                    if cell.tag.endswith("}c") or cell.tag == "c"
                ]
                headers = [text.strip() for _, text in sorted(first_cells, key=lambda item: item[0]) if text.strip()]
                return headers, max(0, len(rows) - 1), None
            return [], 0, "INTAKE_SPREADSHEET_STRUCTURE_UNKNOWN"
    except zipfile.BadZipFile:
        return [], 0, "INTAKE_CORRUPT_OR_UNREADABLE_ATTACHMENT"
    except RuntimeError:
        return [], 0, "INTAKE_ENCRYPTED_ATTACHMENT_UNSUPPORTED"


def _document_kind_flags(text: str, extension_bucket: str) -> dict[str, bool]:
    return {
        "policy_like": any(term in text for term in _POLICY_TERMS),
        "format_like": any(term in text for term in _FORMAT_TERMS),
        "draft_material_like": any(term in text for term in _DRAFT_TERMS),
        "external_convert_like": any(term in text for term in _CONVERT_TERMS),
        "unsupported_hwp_like": extension_bucket in {"hwp", "hwpx"},
    }


@dataclass(frozen=True)
class RuntimeAttachment:
    """Runtime-only attachment input used by tests and non-FastAPI callers."""

    data: bytes
    filename: str | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class AttachmentFeature:
    file_digest: str
    file_kind: str
    feature_digest: str
    extension_bucket: str
    mime_bucket: str
    size_bucket: str
    table_header_digest_set: list[str] = field(default_factory=list)
    column_role_flags: dict[str, bool] = field(default_factory=dict)
    document_kind_flags: dict[str, bool] = field(default_factory=dict)
    row_count_bucket: str | None = None
    page_count_bucket: str | None = None
    audio_duration_bucket: str | None = None
    extractor_fail_class: str | None = None
    dlp_buckets: list[str] = field(default_factory=list)
    raw_text_logged: bool = False
    sample_values_logged: bool = False
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttachmentFeatureBundle:
    schema_version: str
    attachment_count: int
    attachments: list[dict[str, Any]]
    feature_set_digest: str
    unsupported_files: list[dict[str, str]]
    raw_text_logged: bool = False
    sample_values_logged: bool = False
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _infer_spreadsheet_kind(headers: list[str], extension_bucket: str, text_preview: str) -> tuple[str, str | None]:
    header_set = {h.strip() for h in headers if h.strip()}
    matched = len(header_set & _ACCOUNTING_HEADERS)
    flags = _column_role_flags(headers)
    if matched >= 3 or (flags["has_date_column"] and flags["has_amount_column"] and (flags["has_balance_column"] or flags["has_counterparty_column"])):
        return "bank_statement_table", None
    if extension_bucket == "xlsm":
        return "unsupported_file_kind", "INTAKE_MACRO_WORKBOOK_UNSUPPORTED"
    if headers:
        return "generic_dataset", None
    if text_preview and any(token in text_preview for token in ("거래일", "입금", "출금", "잔액")):
        return "bank_statement_table", None
    return "generic_dataset", None


def extract_attachment_feature(data: bytes, *, filename: str | None = None, content_type: str | None = None) -> AttachmentFeature:
    file_digest = sha256_bytes(data)
    extension_bucket = _extension_bucket(filename)
    mime_bucket = _mime_bucket(content_type)
    size_bucket = _size_bucket(len(data))
    dlp: list[str] = []
    extractor_fail_class: str | None = None
    file_kind = "unknown_binary"
    header_digests: list[str] = []
    column_flags: dict[str, bool] = {}
    doc_flags: dict[str, bool] = {}
    row_count_bucket: str | None = None
    page_count_bucket: str | None = None
    audio_duration_bucket: str | None = None

    if not data:
        extractor_fail_class = "INTAKE_ATTACHMENT_EMPTY"
        file_kind = "unsupported_file_kind"
    elif extension_bucket in {"hwp", "hwpx"}:
        file_kind = "unsupported_file_kind"
        extractor_fail_class = "INTAKE_HWP_UNSUPPORTED"
    elif extension_bucket == "xlsm":
        file_kind = "unsupported_file_kind"
        extractor_fail_class = "INTAKE_MACRO_WORKBOOK_UNSUPPORTED"
    elif extension_bucket in {"csv", "tsv"} or (content_type and "csv" in content_type.casefold()):
        preview = _decode_preview(data)
        dlp = _dlp_buckets(preview)
        headers, rows = _spreadsheet_from_csv(preview)
        header_digests = _header_digest_set(headers)
        column_flags = _column_role_flags(headers)
        row_count_bucket = _row_bucket(rows)
        file_kind, extractor_fail_class = _infer_spreadsheet_kind(headers, extension_bucket, preview)
    elif extension_bucket in {"xlsx", "xls"} or mime_bucket == "spreadsheet":
        headers, rows, fail = _spreadsheet_from_xlsx(data)
        if fail:
            file_kind = "unsupported_file_kind" if fail.startswith("INTAKE_") else "generic_dataset"
            extractor_fail_class = fail
        else:
            header_digests = _header_digest_set(headers)
            column_flags = _column_role_flags(headers)
            row_count_bucket = _row_bucket(rows)
            file_kind, extractor_fail_class = _infer_spreadsheet_kind(headers, extension_bucket, "")
    elif extension_bucket in {"m4a", "mp3", "wav", "aac", "flac", "ogg"} or mime_bucket == "audio":
        file_kind = "audio_meeting"
        audio_duration_bucket = "unknown"
    elif extension_bucket in {"txt", "md", "pdf", "docx", "hwp", "hwpx", "rtf"} or mime_bucket in {"pdf", "document", "text"}:
        preview = _decode_preview(data)
        dlp = _dlp_buckets(preview)
        doc_flags = _document_kind_flags(preview, extension_bucket)
        if doc_flags["unsupported_hwp_like"]:
            file_kind = "unsupported_file_kind"
            extractor_fail_class = "INTAKE_HWP_UNSUPPORTED"
        elif doc_flags["policy_like"]:
            file_kind = "company_policy_doc"
        elif doc_flags["format_like"]:
            file_kind = "company_format_template"
        elif doc_flags["external_convert_like"]:
            file_kind = "external_doc_to_convert"
        elif doc_flags["draft_material_like"]:
            file_kind = "draft_source_material"
        else:
            file_kind = "generic_document"
        page_count_bucket = "unknown"
    else:
        # Try a small text decode for DLP bucketing only; do not persist preview.
        preview = _decode_preview(data)
        dlp = _dlp_buckets(preview)
        file_kind = "unsupported_file_kind"
        extractor_fail_class = "INTAKE_UNSUPPORTED_FILE_KIND"

    feature_basis = {
        "file_digest": file_digest,
        "file_kind": file_kind,
        "extension_bucket": extension_bucket,
        "mime_bucket": mime_bucket,
        "size_bucket": size_bucket,
        "table_header_digest_set": header_digests,
        "column_role_flags": column_flags,
        "document_kind_flags": doc_flags,
        "row_count_bucket": row_count_bucket,
        "page_count_bucket": page_count_bucket,
        "audio_duration_bucket": audio_duration_bucket,
        "extractor_fail_class": extractor_fail_class,
        "dlp_buckets": dlp,
        "raw_text_logged": False,
        "sample_values_logged": False,
        "external_send_zero": True,
    }
    feature_digest = stable_json_digest(feature_basis)
    return AttachmentFeature(
        file_digest=file_digest,
        file_kind=file_kind,
        feature_digest=feature_digest,
        extension_bucket=extension_bucket,
        mime_bucket=mime_bucket,
        size_bucket=size_bucket,
        table_header_digest_set=header_digests,
        column_role_flags=column_flags,
        document_kind_flags=doc_flags,
        row_count_bucket=row_count_bucket,
        page_count_bucket=page_count_bucket,
        audio_duration_bucket=audio_duration_bucket,
        extractor_fail_class=extractor_fail_class,
        dlp_buckets=dlp,
    )


def extract_attachment_features(attachments: Sequence[RuntimeAttachment]) -> AttachmentFeatureBundle:
    features = [extract_attachment_feature(item.data, filename=item.filename, content_type=item.content_type) for item in attachments]
    feature_dicts = [f.to_dict() for f in features]
    canonical = sorted(
        [
            {
                "file_digest": f["file_digest"],
                "file_kind": f["file_kind"],
                "feature_digest": f["feature_digest"],
                "extractor_fail_class": f.get("extractor_fail_class"),
                "dlp_buckets": f.get("dlp_buckets", []),
            }
            for f in feature_dicts
        ],
        key=lambda item: (item["file_digest"], item["feature_digest"]),
    )
    unsupported = [
        {
            "file_digest": f["file_digest"],
            "file_kind": f["file_kind"],
            "extractor_fail_class": str(f.get("extractor_fail_class") or "INTAKE_UNSUPPORTED_FILE_KIND"),
        }
        for f in feature_dicts
        if f.get("extractor_fail_class")
    ]
    return AttachmentFeatureBundle(
        schema_version=SCHEMA_VERSION,
        attachment_count=len(feature_dicts),
        attachments=feature_dicts,
        feature_set_digest=stable_json_digest({"attachments": canonical, "schema_version": SCHEMA_VERSION}),
        unsupported_files=unsupported,
    )


def feature_summary_for_decision(bundle: AttachmentFeatureBundle) -> dict[str, Any]:
    """Return the raw-free multi-attachment evidence surface used by IntakeRouter."""
    return {
        "attachment_count": bundle.attachment_count,
        "attachments": [
            {
                "file_digest": item["file_digest"],
                "file_kind": item["file_kind"],
                "feature_digest": item["feature_digest"],
                "extractor_fail_class": item.get("extractor_fail_class"),
                "dlp_buckets": item.get("dlp_buckets", []),
                "raw_text_logged": False,
                "sample_values_logged": False,
            }
            for item in bundle.attachments
        ],
        "feature_set_digest": bundle.feature_set_digest,
        "unsupported_files": bundle.unsupported_files,
        "raw_text_logged": False,
        "sample_values_logged": False,
        "external_send_zero": True,
    }
