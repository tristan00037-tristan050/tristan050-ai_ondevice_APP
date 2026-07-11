from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path
from typing import Any

from .contracts import is_sha256, stable_digest, validate_reason_code


ALLOWED_SHADOW_KEYS = frozenset(
    {
        "schema_version",
        "timestamp_epoch_ms",
        "request_digest",
        "box_id",
        "task_profile_digest",
        "device_profile_digest",
        "policy_digest",
        "decision_digest",
        "recommended_tier",
        "recommended_variant_id",
        "reason_codes",
        "high_eligible",
        "gate_reason_code",
        "would_escalate",
        "actual_model_selection_unchanged",
        "actual_response_digest",
        "raw_text_logged",
        "external_send_zero",
        "previous_record_digest",
        "record_digest",
    }
)
_DIGEST_KEYS = frozenset(
    {
        "request_digest",
        "task_profile_digest",
        "device_profile_digest",
        "policy_digest",
        "decision_digest",
        "actual_response_digest",
        "previous_record_digest",
        "record_digest",
    }
)


def default_shadow_audit_path() -> Path:
    return Path.home() / ".butler" / "audit" / "model_tier_shadow_v1.jsonl"


def validate_shadow_record(record: dict[str, Any], *, verify_record_digest: bool = True) -> None:
    if set(record) != ALLOWED_SHADOW_KEYS:
        raise ValueError("SHADOW_RECORD_EXACT_KEYS_REQUIRED")
    if record.get("schema_version") != "butler.model_tier_shadow.v1":
        raise ValueError("SHADOW_RECORD_SCHEMA_INVALID")
    if record.get("box_id") not in {"1", "3"}:
        raise ValueError("SHADOW_RECORD_BOX_INVALID")
    if not isinstance(record.get("timestamp_epoch_ms"), int) or record["timestamp_epoch_ms"] < 0:
        raise ValueError("SHADOW_RECORD_TIMESTAMP_INVALID")
    if any(not is_sha256(record.get(key)) for key in _DIGEST_KEYS):
        raise ValueError("SHADOW_RECORD_DIGEST_INVALID")
    if record.get("recommended_tier") not in {"MODEL_NONE", "TIER_1P7B", "TIER_4B"}:
        raise ValueError("SHADOW_RECORD_TIER_INVALID")
    variant_id = record.get("recommended_variant_id")
    if variant_id is not None and (
        not isinstance(variant_id, str)
        or not variant_id
        or len(variant_id) > 128
        or "/" in variant_id
        or "\\" in variant_id
    ):
        raise ValueError("SHADOW_RECORD_VARIANT_INVALID")
    reasons = record.get("reason_codes")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError("SHADOW_RECORD_REASONS_REQUIRED")
    for reason in reasons:
        if not isinstance(reason, str):
            raise ValueError("SHADOW_RECORD_REASON_INVALID")
        validate_reason_code(reason)
    gate_reason = record.get("gate_reason_code")
    if gate_reason is not None:
        if not isinstance(gate_reason, str):
            raise ValueError("SHADOW_RECORD_GATE_REASON_INVALID")
        validate_reason_code(gate_reason)
    for key in ("high_eligible", "would_escalate"):
        if not isinstance(record.get(key), bool):
            raise ValueError("SHADOW_RECORD_BOOLEAN_INVALID")
    if record.get("raw_text_logged") is not False or record.get("external_send_zero") is not True:
        raise ValueError("SHADOW_RECORD_SAFETY_FLAGS_INVALID")
    if record.get("actual_model_selection_unchanged") is not True:
        raise ValueError("PHASE0_MODEL_SELECTION_CHANGED")
    if verify_record_digest:
        unsigned = dict(record)
        claimed = unsigned.pop("record_digest")
        if stable_digest(unsigned) != claimed:
            raise ValueError("SHADOW_RECORD_DIGEST_MISMATCH")


def build_shadow_record(
    *,
    timestamp_epoch_ms: int,
    request_digest: str,
    box_id: str,
    task_profile_digest: str,
    device_profile_digest: str,
    policy_digest: str,
    decision_digest: str,
    recommended_tier: str,
    recommended_variant_id: str | None,
    reason_codes: tuple[str, ...],
    high_eligible: bool,
    gate_reason_code: str | None,
    would_escalate: bool,
    actual_response_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": "butler.model_tier_shadow.v1",
        "timestamp_epoch_ms": timestamp_epoch_ms,
        "request_digest": request_digest,
        "box_id": box_id,
        "task_profile_digest": task_profile_digest,
        "device_profile_digest": device_profile_digest,
        "policy_digest": policy_digest,
        "decision_digest": decision_digest,
        "recommended_tier": recommended_tier,
        "recommended_variant_id": recommended_variant_id,
        "reason_codes": list(reason_codes),
        "high_eligible": high_eligible,
        "gate_reason_code": gate_reason_code,
        "would_escalate": would_escalate,
        "actual_model_selection_unchanged": True,
        "actual_response_digest": actual_response_digest,
        "raw_text_logged": False,
        "external_send_zero": True,
    }


def _assert_no_symlink_components(path: Path) -> None:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError("AUDIT_PATH_SYMLINK_FORBIDDEN")


class HashChainJsonlWriter:
    def __init__(self, path: Path, *, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.path = path.expanduser().absolute()
        self.max_bytes = int(max_bytes)
        if self.max_bytes <= 1024:
            raise ValueError("AUDIT_MAX_BYTES_INVALID")
        self._lock = threading.Lock()
        self._previous_digest = "sha256:" + "0" * 64
        self._ensure_parent()
        self._recover_previous_digest()

    def _ensure_parent(self) -> None:
        _assert_no_symlink_components(self.path.parent)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _assert_no_symlink_components(self.path.parent)
        if not self.path.parent.is_dir():
            raise ValueError("AUDIT_PARENT_NOT_DIRECTORY")
        os.chmod(self.path.parent, 0o700)

    def _recover_previous_digest(self) -> None:
        if not self.path.exists():
            return
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("AUDIT_PATH_INVALID")
        with self.path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 131_072))
            lines = handle.read().splitlines()
        if not lines:
            return
        try:
            last = json.loads(lines[-1].decode("utf-8"))
        except Exception as exc:
            raise ValueError("AUDIT_TAIL_INVALID") from exc
        validate_shadow_record(last)
        self._previous_digest = last["record_digest"]

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if incoming_bytes > self.max_bytes:
            raise ValueError("AUDIT_RECORD_TOO_LARGE")
        if not self.path.exists() or self.path.stat().st_size + incoming_bytes <= self.max_bytes:
            return
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("AUDIT_PATH_INVALID")
        rotated = self.path.with_name(self.path.name + ".1")
        if rotated.exists() and (rotated.is_symlink() or not rotated.is_file()):
            raise ValueError("AUDIT_ROTATION_TARGET_INVALID")
        os.replace(self.path, rotated)
        os.chmod(rotated, 0o600)

    def append(self, record: dict[str, Any]) -> str:
        with self._lock:
            self._ensure_parent()
            base = dict(record)
            if set(base) & {"previous_record_digest", "record_digest"}:
                raise ValueError("AUDIT_CHAIN_FIELDS_CALLER_FORBIDDEN")
            base["previous_record_digest"] = self._previous_digest
            base["record_digest"] = stable_digest(base)
            validate_shadow_record(base)
            encoded = (
                json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            self._rotate_if_needed(len(encoded))
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            try:
                mode = os.fstat(fd).st_mode
                if not stat.S_ISREG(mode):
                    raise ValueError("AUDIT_TARGET_NOT_REGULAR_FILE")
                os.fchmod(fd, 0o600)
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
            self._previous_digest = str(base["record_digest"])
            return self._previous_digest
