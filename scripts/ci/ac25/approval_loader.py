"""§E7-1 승인서 엄격 로더 (production).

원격에서 읽은 승인 문서 원문 바이트를 CrossTrackApprovalV2 로 만든다.
지금까지 이 구조체는 시험 코드에서만 만들어졌다 — production 경로가 없었다.

엄격 규칙
  · 알려진 키만 읽는다. 키가 빠지거나 두 번 나오면 닫는다.
  · ★issued_at 을 문서에서 읽지 않는다(§E3). 문서가 issued_at 에 시각을
    적어 두면 그것 자체를 위반으로 닫는다. 시각 정본은 승인 커밋 committer 다.
  · document_sha256·approval_commit_sha·source_repo·protected_ref·document_path 는
    문서가 스스로 선언할 수 없는 값이다. 문서에서 읽지 않고, 바이트를 실제로
    가져온 곳(측정값)과 고정 지문에서 받는다. 그래야 신뢰원 대조가 자기증명이
    되지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .cross_track_approval import SCHEMA_VERSION, CrossTrackApprovalV2

APPROVAL_DOCUMENT_MALFORMED = "APPROVAL_DOCUMENT_MALFORMED"
APPROVAL_DOCUMENT_TIME_DECLARED = "APPROVAL_DOCUMENT_TIME_DECLARED"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# 후보 저장소 경로(승인 경로 여섯)는 ASCII 다. 산문 줄과 확실히 구분된다.
_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
# 승인 저장소의 문서 경로는 한글을 포함한다. 공백·제어문자만 금지한다.
_DOC_PATH_RE = re.compile(r"^[^\s\x00]+/[^\s\x00]+$")
_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")

# 문서가 선언해야 하는 키. 이 밖의 키는 읽지 않는다.
_SCALAR_KEYS = (
    "integration_base_sha",
    "provenance_base_sha",
    "provenance_base_tree",
    "candidate_head_sha",
    "candidate_head_tree",
    "identity_artifact_zip_sha256",
    "identity_manifest_sha256",
    "expires_at",
    "approver_login",
    "approver_id",
    "signing_key",
    "namespace",
    "signature_file",
    "allowed_signers",
)

# ★§E3: 문서에 시각을 적어 두면 그 자체가 위반이다.
_DECLARED_TIME_RE = re.compile(r"^issued_at\s+\d{4}-\d{2}-\d{2}T")

_PATHS_HEADING = "## 3."


class ApprovalDocumentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DocumentOrigin:
    """바이트를 ★실제로 가져온 곳. API 응답에서 측정한 값이며 상수 복사가 아니다."""
    repository: str
    protected_ref: str
    document_path: str
    approval_commit_sha: str


def _fail(message: str) -> ApprovalDocumentError:
    return ApprovalDocumentError(APPROVAL_DOCUMENT_MALFORMED, message)


def _scalars(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if _DECLARED_TIME_RE.match(stripped):
            raise ApprovalDocumentError(
                APPROVAL_DOCUMENT_TIME_DECLARED,
                "문서가 issued_at 에 시각을 적었다 — 시각 정본은 승인 커밋 committer 다(§E3)",
            )
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0], parts[1].strip()
        if key not in _SCALAR_KEYS:
            continue
        if key in found:
            raise _fail(f"키가 두 번 나온다: {key}")
        found[key] = value
    missing = [key for key in _SCALAR_KEYS if key not in found]
    if missing:
        raise _fail(f"필수 키 누락: {missing}")
    return found


def _approved_paths(lines: list[str]) -> tuple[str, ...]:
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(_PATHS_HEADING)), None
    )
    if start is None:
        raise _fail(f"승인 경로 절({_PATHS_HEADING})이 없다")
    collected: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped or not _REPO_PATH_RE.match(stripped) or "/" not in stripped:
            continue
        collected.append(stripped)
    if not collected:
        raise _fail("승인 경로가 하나도 없다")
    if len(set(collected)) != len(collected):
        raise _fail("승인 경로에 중복이 있다")
    return tuple(sorted(collected))


def _require(pattern: re.Pattern[str], key: str, value: str) -> str:
    if not pattern.match(value):
        raise _fail(f"{key} 형식 오류: {value!r}")
    return value


def load_approval_document(
    document_bytes: bytes,
    *,
    origin: DocumentOrigin,
    pinned_document_sha256: str,
) -> CrossTrackApprovalV2:
    """승인 문서 원문에서 v2 승인서를 엄격 로드한다."""
    if not document_bytes:
        raise _fail("문서 바이트가 비어 있다")
    try:
        text = document_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(f"UTF-8 디코딩 실패: {exc}") from exc

    lines = text.splitlines()
    values = _scalars(lines)
    paths = _approved_paths(lines)

    approver_id_raw = values["approver_id"]
    if not approver_id_raw.isdigit():
        raise _fail(f"approver_id 는 정수여야 한다: {approver_id_raw!r}")

    return CrossTrackApprovalV2(
        schema_version=SCHEMA_VERSION,
        integration_base_sha=_require(_OID_RE, "integration_base_sha", values["integration_base_sha"]),
        provenance_base_sha=_require(_OID_RE, "provenance_base_sha", values["provenance_base_sha"]),
        provenance_base_tree=_require(_OID_RE, "provenance_base_tree", values["provenance_base_tree"]),
        candidate_head_sha=_require(_OID_RE, "candidate_head_sha", values["candidate_head_sha"]),
        candidate_head_tree=_require(_OID_RE, "candidate_head_tree", values["candidate_head_tree"]),
        identity_artifact_zip_sha256=_require(
            _SHA256_RE, "identity_artifact_zip_sha256", values["identity_artifact_zip_sha256"]
        ),
        identity_manifest_sha256=_require(
            _SHA256_RE, "identity_manifest_sha256", values["identity_manifest_sha256"]
        ),
        approved_paths=frozenset(paths),
        # ↓ 문서가 스스로 선언할 수 없는 값 — 측정값·고정 지문에서 받는다
        source_repo=origin.repository,
        protected_ref=origin.protected_ref,
        document_path=origin.document_path,
        approval_commit_sha=origin.approval_commit_sha,
        document_sha256=_require(_SHA256_RE, "pinned_document_sha256", pinned_document_sha256),
        approver_login=values["approver_login"],
        approver_id=int(approver_id_raw),
        signature_path=_require(_DOC_PATH_RE, "signature_file", values["signature_file"]),
        allowed_signers_path=_require(_DOC_PATH_RE, "allowed_signers", values["allowed_signers"]),
        signing_key_fingerprint=_require(_FINGERPRINT_RE, "signing_key", values["signing_key"]),
        signature_namespace=values["namespace"],
        expires_at=_require(_UTC_RE, "expires_at", values["expires_at"]),
    )


__all__ = [
    "APPROVAL_DOCUMENT_MALFORMED",
    "APPROVAL_DOCUMENT_TIME_DECLARED",
    "ApprovalDocumentError",
    "DocumentOrigin",
    "load_approval_document",
]
