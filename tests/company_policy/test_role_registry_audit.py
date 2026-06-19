from __future__ import annotations

import json

import pytest

from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.company_policy.role_registry_audit import RoleRegistryAuditLoadError, RoleRegistryAuditStore


def _append(store: RoleRegistryAuditStore, label: str):
    return store.append(
        action=f"role_registry.{label}",
        target_admin_id_digest=sha256_text(f"target-{label}"),
        actor_digest=sha256_text("actor"),
        entry_digest=sha256_text(f"entry-{label}"),
        reason_code=f"{label.upper()}_REASON",
    )


def test_audit_persists_log_head_and_restores_chain(tmp_path):
    store = RoleRegistryAuditStore(root=tmp_path)
    first = _append(store, "first")
    second = _append(store, "second")

    restored = RoleRegistryAuditStore(root=tmp_path)

    assert len(restored.records) == 2
    assert restored.records[0]["audit_id"] == first["audit_id"]
    assert restored.records[1]["prev_audit_digest"] == first["audit_id"]
    assert restored.records[1]["audit_id"] == second["audit_id"]
    head = json.loads((tmp_path / "role_registry_audit_head.json").read_text(encoding="utf-8"))
    assert head["record_count"] == 2
    assert head["last_audit_id"] == second["audit_id"]


def test_two_instances_refresh_persisted_state_before_append(tmp_path):
    first_store = RoleRegistryAuditStore(root=tmp_path)
    second_store = RoleRegistryAuditStore(root=tmp_path)

    first = _append(first_store, "first")
    second = _append(second_store, "second")

    assert second["sequence"] == 2
    assert second["prev_audit_digest"] == first["audit_id"]
    assert len(RoleRegistryAuditStore(root=tmp_path).records) == 2


def test_audit_tamper_and_truncation_fail_closed(tmp_path):
    store = RoleRegistryAuditStore(root=tmp_path)
    _append(store, "first")
    _append(store, "second")

    log_path = tmp_path / "role_registry_audit_log.jsonl"
    rows = log_path.read_text(encoding="utf-8").splitlines()
    changed = json.loads(rows[0])
    changed["reason_code"] = "TAMPERED"
    rows[0] = json.dumps(changed, sort_keys=True)
    log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(RoleRegistryAuditLoadError):
        RoleRegistryAuditStore(root=tmp_path)

    log_path.write_text("\n".join(rows), encoding="utf-8")
    with pytest.raises(RoleRegistryAuditLoadError):
        RoleRegistryAuditStore(root=tmp_path)
