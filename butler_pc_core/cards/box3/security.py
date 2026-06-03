from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


FORBIDDEN_RAW_KEYS = {
    "raw",
    "raw_doc",
    "raw_text",
    "raw_output",
    "reference_doc",
    "reference_docs",
    "source_doc_name",
    "filename",
    "file_name",
    "file_path",
    "absolute_path",
    "absolute_local_path",
    "local_uri",
    "prompt",
    "input_text",
    "foreign_doc",
    "our_format",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_KOREAN_RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[- .]?)?(?:\(?0?\d{1,3}\)?[- .]?)?\d{3,4}[- .]?\d{4}(?!\d)")
_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{10,}|api[_-]?key\s*[:=]\s*\S+|"
    r"token\s*[:=]\s*\S+|secret\s*[:=]\s*\S+|password\s*[:=]\s*\S+|"
    r"sk-[a-z0-9][a-z0-9_-]{10,})"
)
_LOCAL_PATH_RE = re.compile(
    r"(?i)(file://|/Users/|/home/|/private/tmp|/tmp/|/Volumes/|"
    r"(?<![A-Za-z0-9])[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+\\)"
)
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_DIGEST_INLINE_RE = re.compile(r"sha256:[a-f0-9]{64}")
# 박스 3 real asset 최종 (2026-06-03): asset_manifest 의 helper SHA 상수(HELPER{3,4,7,8}_SHA)는
# 64-hex 만으로 저장되어 `sha256:` prefix 가 없다. evidence persist 시 PII regex(특히 PHONE)와
# false-positive 가 발생해 자체 SHA 가 차단되던 결함을 해소하기 위해 64-hex 단독 문자열도
# SHA 인식 대상으로 추가한다 (보안 완화 아님 — sha256 인식 형식 확장).
_BARE_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")


class Box3SecurityError(ValueError):
    """Raised when a raw document, local path, PII, or secret would persist."""


def sha256_digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.fullmatch(value))


def scan_forbidden_text(value: str) -> list[str]:
    findings: list[str] = []
    scan_value = _DIGEST_INLINE_RE.sub("sha256:DIGEST", value)
    checks = (
        ("PII_EMAIL", _EMAIL_RE),
        ("PII_KOREAN_RRN", _KOREAN_RRN_RE),
        ("PII_PHONE", _PHONE_RE),
        ("PII_CARD_OR_ACCOUNT", _CARD_OR_ACCOUNT_RE),
        ("SECRET", _SECRET_RE),
        ("LOCAL_PATH", _LOCAL_PATH_RE),
    )
    for name, pattern in checks:
        if pattern.search(scan_value):
            findings.append(name)
    return findings


def assert_runtime_text_safe(value: str) -> None:
    findings = scan_forbidden_text(value)
    if findings:
        raise Box3SecurityError("BLOCK_RUNTIME_TEXT_FORBIDDEN:" + ",".join(findings))


def assert_no_raw_persistence(payload: Any, path: str = "$") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key) in FORBIDDEN_RAW_KEYS:
                raise Box3SecurityError(f"BLOCK_RAW_KEY:{path}.{key}")
            assert_no_raw_persistence(value, f"{path}.{key}")
        return
    if isinstance(payload, str):
        findings = scan_forbidden_text(payload)
        if findings and not is_sha256_digest(payload) and not _BARE_SHA256_HEX_RE.fullmatch(payload):
            raise Box3SecurityError(f"BLOCK_FORBIDDEN_SCALAR:{path}:{','.join(findings)}")
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        for index, value in enumerate(payload):
            assert_no_raw_persistence(value, f"{path}[{index}]")


def stable_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_digest(encoded)
