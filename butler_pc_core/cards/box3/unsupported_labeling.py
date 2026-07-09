from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .actual_contracts import sha256_text
from .actual_fail_class import BLOCK_DLP_OUTBOUND_DRAFT, NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL
from .helper_sdk_bridge import _normalize_claim_line_for_helper4
from .security import scan_forbidden_text

LABEL_PREFIX = "[근거 확인 필요] "
FULL_REVIEW_BANNER = "[전체 검토 필요] 근거가 확인되지 않은 문장이 있어 사람이 반드시 검토해야 합니다."

_LINE_PREFIX_RE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)]|[가-힣]\.)\s*")


@dataclass(frozen=True)
class UnsupportedLabelMeta:
    unsupported_claim_count: int
    annotated_claim_count: int
    label_coverage_ok: bool
    label_banner_applied: bool
    review_reason_code: str | None
    raw_text_logged: bool = False
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DlpOutboundVerdict:
    blocked: bool
    reason_code: str | None = None
    finding_count: int = 0
    raw_text_logged: bool = False
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_draft_claim_line(line: str) -> str:
    value = str(line or "").strip()
    if not value:
        return ""
    value = _LINE_PREFIX_RE.sub("", value)
    value = value.split(":", 1)[-1].strip() if ":" in value[:24] else value
    return " ".join(value.split())


def _digest_candidates(line: str) -> set[str]:
    candidates = {line.strip(), normalize_draft_claim_line(line)}
    try:
        helper4_line = _normalize_claim_line_for_helper4(line)
        candidates.add(helper4_line)
        candidates.add(helper4_line.split(":", 1)[-1].strip() if ":" in helper4_line[:64] else helper4_line)
    except Exception:
        pass
    return {sha256_text(item) for item in candidates if item}


def unsupported_digest_set(claim_verdicts: Iterable[Any]) -> set[str]:
    return {
        str(getattr(verdict, "claim_digest", ""))
        for verdict in claim_verdicts
        if getattr(verdict, "support_level", None) == "unsupported" and str(getattr(verdict, "claim_digest", ""))
    }


def _claim_candidate_line_indices(lines: list[str]) -> list[int]:
    return [index for index, line in enumerate(lines) if normalize_draft_claim_line(line)]


def _with_label(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(LABEL_PREFIX):
        return line
    leading = line[: len(line) - len(stripped)]
    return leading + LABEL_PREFIX + stripped


def annotate_unsupported_lines(draft_text: str, unsupported_digests: set[str]) -> tuple[str, UnsupportedLabelMeta]:
    if not unsupported_digests:
        return draft_text, UnsupportedLabelMeta(0, 0, True, False, None)

    lines = str(draft_text or "").splitlines()
    matched_indices: set[int] = set()
    for index, line in enumerate(lines):
        if _digest_candidates(line) & unsupported_digests:
            matched_indices.add(index)

    label_coverage_ok = len(matched_indices) >= len(unsupported_digests)
    label_banner_applied = False
    if not label_coverage_ok:
        matched_indices = set(_claim_candidate_line_indices(lines))
        label_banner_applied = True

    annotated_lines = [(_with_label(line) if index in matched_indices else line) for index, line in enumerate(lines)]
    annotated = "\n".join(annotated_lines)
    reason_code = None if label_coverage_ok else NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL
    if label_banner_applied:
        annotated = f"{FULL_REVIEW_BANNER}\n{annotated}" if annotated else FULL_REVIEW_BANNER

    return annotated, UnsupportedLabelMeta(
        unsupported_claim_count=len(unsupported_digests),
        annotated_claim_count=len(matched_indices),
        label_coverage_ok=label_coverage_ok,
        label_banner_applied=label_banner_applied,
        review_reason_code=reason_code,
    )


def scan_outbound_text_for_pii_or_secret(value: str) -> DlpOutboundVerdict:
    findings = scan_forbidden_text(str(value or ""))
    if findings:
        return DlpOutboundVerdict(True, BLOCK_DLP_OUTBOUND_DRAFT, len(findings))
    return DlpOutboundVerdict(False)
