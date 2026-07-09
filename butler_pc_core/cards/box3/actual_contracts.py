from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .actual_fail_class import ALLOWED_ACTUAL_OPERATION_STATUSES

Digest = str
ActualStatus = Literal[
    "CONTRACT_ONLY",
    "ASSET_INVENTORY_PASS",
    "PARTIAL_REAL_ASSET_VOLUME_MISSING",
    "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE",
    "PARTIAL_HELPER_STACK_UNSUPPORTED",
    "PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED",
    "PARTIAL_HELPER_SDK_UNAVAILABLE",
    "PARTIAL_EMBEDDER_UNAVAILABLE",
    "PARTIAL_BGE_M3_FALLBACK_USED",
    "REAL_CANDIDATE",
    "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL",
    "BLOCKED",
]

_SHA_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_BARE_SHA_RE = re.compile(r"^[a-f0-9]{64}$")
_FORBIDDEN_SCALARS = (
    "/" + "Users/",
    "/" + "home/",
    "/" + "Volumes/",
    "sk-" + "proj-",
    "BEGIN" + " PRIVATE KEY",
    "api_key",
)
_FORBIDDEN_KEYS = (
    "raw",
    "prompt",
    "reference_text",
    "draft_text_runtime",
    "absolute_path",
    "file_path",
)

def sha256_text(text: str) -> Digest:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha256_bytes(data: bytes) -> Digest:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def stable_json_digest(value: Any) -> Digest:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(encoded)

def is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))

def is_bare_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_BARE_SHA_RE.fullmatch(value))

def is_canonical_sha256(value: object) -> bool:
    """`sha256:<64 lowerhex>` 정규형 여부(is_sha256_digest 와 동일 계약의 명시 별칭)."""
    return is_sha256_digest(value)

def canonical_sha256(value: str) -> str:
    """이미 계산된 digest(bare hex 또는 sha256:hex)를 정규형 `sha256:<64 lowerhex>` 로 만든다.

    원문을 재해싱하지 않는다 — 파일 sha256 hexdigest 를 manifest/런타임과 동일 규칙으로
    비교하기 위한 정규화 전용이다. 형식 위반은 ValueError('NON_CANONICAL_SHA256').
    """
    if not isinstance(value, str):
        raise ValueError("NON_CANONICAL_SHA256")
    lowered = value.strip().lower()
    if lowered.startswith("sha256:"):
        lowered = lowered[len("sha256:") :]
    if not _BARE_SHA_RE.fullmatch(lowered):
        raise ValueError("NON_CANONICAL_SHA256")
    return "sha256:" + lowered

def assert_persistable_digest_only(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    lowered = encoded.casefold()
    for key in _FORBIDDEN_KEYS:
        if key.casefold() in lowered and "raw_saved_zero" not in lowered:
            raise AssertionError(f"raw-like key leaked: {key}")
    for item in _FORBIDDEN_SCALARS:
        if item in encoded:
            raise AssertionError(f"forbidden scalar leaked: {item}")

@dataclass
class Box3ActualRuntimeEnvelope:
    request_id: str
    reference_text_runtime_only: list[str] = field(default_factory=list, repr=False)
    drafting_request_runtime_only: str = field(default="", repr=False)
    format_hint: str = "자유형"
    max_new_tokens: int = 512
    policy_gate_allowed: bool = True

    @classmethod
    def from_raw(
        cls,
        *,
        drafting_request: str,
        reference_texts: list[str] | tuple[str, ...],
        format_hint: str = "자유형",
        max_new_tokens: int = 512,
        request_id: str | None = None,
        policy_gate_allowed: bool = True,
    ) -> "Box3ActualRuntimeEnvelope":
        if not reference_texts:
            raise ValueError("REFERENCE_TEXTS_REQUIRED")
        if not isinstance(drafting_request, str) or not drafting_request.strip():
            raise ValueError("DRAFTING_REQUEST_REQUIRED")
        if not isinstance(max_new_tokens, int) or max_new_tokens < 1:
            raise ValueError("MAX_NEW_TOKENS_INVALID")
        for text in [drafting_request, format_hint, *reference_texts]:
            if not isinstance(text, str):
                raise ValueError("RUNTIME_TEXT_INVALID")
        return cls(
            request_id=request_id or str(uuid.uuid4()),
            reference_text_runtime_only=list(reference_texts),
            drafting_request_runtime_only=drafting_request,
            format_hint=format_hint,
            max_new_tokens=max_new_tokens,
            policy_gate_allowed=policy_gate_allowed,
        )

    @property
    def reference_digests(self) -> list[Digest]:
        return [sha256_text(text) for text in self.reference_text_runtime_only]

    @property
    def request_digest(self) -> Digest:
        return stable_json_digest({
            "drafting_request_digest": sha256_text(self.drafting_request_runtime_only),
            "reference_digests": self.reference_digests,
            "format_hint_digest": sha256_text(self.format_hint),
            "max_new_tokens": self.max_new_tokens,
        })

    def to_audit_seed(self) -> dict[str, Any]:
        payload = {
            "request_digest": self.request_digest,
            "reference_digests": self.reference_digests,
            "external_send_zero": True,
            "raw_saved_zero": True,
        }
        assert_persistable_digest_only(payload)
        return payload

@dataclass(frozen=True)
class Box3ActualOperationVerdict:
    schema_version: str
    request_id: str
    request_digest: Digest
    status: ActualStatus | str
    draft_text: str | None
    draft_digest: Digest | None
    metrics: dict[str, Any]
    citations: list[dict[str, str]]
    stage_trace: list[dict[str, Any]]
    fail_class: str | None
    real_claim_allowed: bool
    human_approval_required: bool
    runner_measurements: dict[str, Any]
    asset_measurements: dict[str, Any]
    helper_sdk_receipts: dict[str, Any] | None = None
    review_reason_code: str | None = None
    unsupported_claim_count: int = 0
    annotated_claim_count: int = 0
    label_coverage_ok: bool = True
    labeling_applied: bool = False
    label_banner_applied: bool = False
    external_send_zero: Literal[True] = True
    raw_saved_zero: Literal[True] = True
    raw_text_logged: Literal[False] = False

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_ACTUAL_OPERATION_STATUSES:
            raise ValueError("BOX3_ACTUAL_STATUS_DRIFT")

    def to_response_dict(self) -> dict[str, Any]:
        return asdict(self)
