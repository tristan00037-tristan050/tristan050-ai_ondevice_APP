from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps tests importable.
    fcntl = None  # type: ignore[assignment]

from .contracts import now_utc, require_digest, stable_json_digest


class RoleRegistryAuditLoadError(RuntimeError):
    pass


AUDIT_RECORD_KEYS = {
    "schema_version",
    "audit_id",
    "sequence",
    "prev_audit_digest",
    "action",
    "target_admin_id_digest",
    "actor_digest",
    "entry_digest",
    "reason_code",
    "created_at",
    "raw_text_logged",
    "external_send_zero",
}
AUDIT_HEAD_KEYS = {
    "schema_version",
    "record_count",
    "last_audit_id",
    "raw_text_logged",
    "external_send_zero",
}


class RoleRegistryAuditStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.log_path = root / "role_registry_audit_log.jsonl" if root is not None else None
        self.head_path = root / "role_registry_audit_head.json" if root is not None else None
        self.lock_path = root / "role_registry_audit.lock" if root is not None else None
        self.records: list[dict[str, Any]] = []
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def clear(self) -> None:
        if self.root is not None:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_CLEAR_UNSUPPORTED")
        self.records.clear()

    def _record_digest(self, record: dict[str, Any]) -> str:
        unsigned = dict(record)
        unsigned.pop("audit_id", None)
        return stable_json_digest(unsigned)

    def _validate_record(self, record: Any, *, sequence: int, previous_id: str | None) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_RECORD_NOT_OBJECT")
        if set(record) != AUDIT_RECORD_KEYS:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_RECORD_FIELDS_INVALID")
        if record.get("schema_version") != "company_policy.role_registry_audit.v1":
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_SCHEMA_INVALID")
        if record.get("sequence") != sequence:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_SEQUENCE_INVALID")
        if record.get("prev_audit_digest") != previous_id:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_PREV_DIGEST_INVALID")
        require_digest(record.get("target_admin_id_digest"), "target_admin_id")
        require_digest(record.get("actor_digest"), "actor")
        require_digest(record.get("entry_digest"), "entry")
        if not isinstance(record.get("action"), str) or not record["action"]:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_ACTION_INVALID")
        if not isinstance(record.get("reason_code"), str) or not record["reason_code"]:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_REASON_INVALID")
        if not isinstance(record.get("created_at"), str) or not record["created_at"]:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_CREATED_AT_INVALID")
        if record.get("raw_text_logged") is not False:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_RAW_TEXT_LOGGED")
        if record.get("external_send_zero") is not True:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_EXTERNAL_SEND_REQUIRED")
        audit_id = record.get("audit_id")
        if audit_id != self._record_digest(record):
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_DIGEST_MISMATCH")
        require_digest(audit_id, "audit")
        return record

    def _validate_head(self, head: Any, *, record_count: int, last_audit_id: str | None) -> None:
        if not isinstance(head, dict):
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_NOT_OBJECT")
        if set(head) != AUDIT_HEAD_KEYS:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_FIELDS_INVALID")
        if head.get("schema_version") != "company_policy.role_registry_audit_head.v1":
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_SCHEMA_INVALID")
        if head.get("record_count") != record_count:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_COUNT_MISMATCH")
        if head.get("last_audit_id") != last_audit_id:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_LAST_MISMATCH")
        if head.get("raw_text_logged") is not False:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_RAW_TEXT_LOGGED")
        if head.get("external_send_zero") is not True:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_EXTERNAL_SEND_REQUIRED")

    def _load_from_disk(self) -> None:
        if self.log_path is None or self.head_path is None:
            return
        try:
            if not self.log_path.exists():
                if self.head_path.exists():
                    head = json.loads(self.head_path.read_text(encoding="utf-8"))
                    self._validate_head(head, record_count=0, last_audit_id=None)
                self.records = []
                return
            loaded: list[dict[str, Any]] = []
            previous_id: str | None = None
            with self.log_path.open("r", encoding="utf-8") as handle:
                for sequence, line in enumerate(handle, start=1):
                    if not line.endswith("\n"):
                        raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_LINE_TRUNCATED")
                    text = line.strip()
                    if not text:
                        raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_LINE_EMPTY")
                    record = self._validate_record(json.loads(text), sequence=sequence, previous_id=previous_id)
                    loaded.append(record)
                    previous_id = record["audit_id"]
            if not self.head_path.exists():
                raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_HEAD_MISSING")
            head = json.loads(self.head_path.read_text(encoding="utf-8"))
            self._validate_head(head, record_count=len(loaded), last_audit_id=previous_id)
            self.records = loaded
        except RoleRegistryAuditLoadError:
            raise
        except Exception as exc:
            raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_LOAD_FAILED") from exc

    def _write_head(self, head: dict[str, Any]) -> None:
        if self.head_path is None:
            return
        temp_path = self.head_path.with_name(self.head_path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(head, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self.head_path)

    @contextlib.contextmanager
    def _exclusive_append_lock(self):
        if self.lock_path is None or fcntl is None:
            yield
            return
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def append(
        self,
        *,
        action: str,
        target_admin_id_digest: str,
        actor_digest: str,
        entry_digest: str,
        reason_code: str,
    ) -> dict[str, Any]:
        require_digest(target_admin_id_digest, "target_admin_id")
        require_digest(actor_digest, "actor")
        require_digest(entry_digest, "entry")
        with self._exclusive_append_lock():
            if self.root is not None:
                self._load_from_disk()
            sequence = len(self.records) + 1
            previous_id = self.records[-1]["audit_id"] if self.records else None
            record = {
                "schema_version": "company_policy.role_registry_audit.v1",
                "sequence": sequence,
                "prev_audit_digest": previous_id,
                "action": action,
                "target_admin_id_digest": target_admin_id_digest,
                "actor_digest": actor_digest,
                "entry_digest": entry_digest,
                "reason_code": reason_code,
                "created_at": now_utc(),
                "raw_text_logged": False,
                "external_send_zero": True,
            }
            record["audit_id"] = self._record_digest(record)
            self._validate_record(record, sequence=sequence, previous_id=previous_id)
            if self.log_path is not None:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                self._write_head(
                    {
                        "schema_version": "company_policy.role_registry_audit_head.v1",
                        "record_count": sequence,
                        "last_audit_id": record["audit_id"],
                        "raw_text_logged": False,
                        "external_send_zero": True,
                    }
                )
            self.records.append(record)
            return record
