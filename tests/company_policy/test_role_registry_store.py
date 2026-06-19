from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryLoadError, RoleRegistryMutationError, RoleRegistryStore
from butler_pc_core.company_policy.role_registry_contracts import RoleRegistryIndexEntry


def _admin(name: str = "admin", role: str = "admin") -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text(name),
        role=role,  # type: ignore[arg-type]
        admin_session_digest=sha256_text(f"{name}-session"),
        auth_method="tauri_secure_invoke",
    )


def test_bootstrap_self_admin_once_and_lookup_active(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")
    entry, audit = store.bootstrap_self_admin(_admin())

    assert entry.status == "ACTIVE"
    assert entry.role == "admin"
    assert audit["reason_code"] == "INITIAL_SETUP_SELF_ADMIN"
    assert store.lookup_active(_admin().admin_id_digest).role == "admin"
    assert store.status_summary()["active_admin_count"] == 1
    with pytest.raises(RoleRegistryMutationError, match="ALREADY_INITIALIZED"):
        store.bootstrap_self_admin(_admin("other"))


def test_concurrent_bootstrap_has_single_winner(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")

    def run(name: str) -> str:
        try:
            store.bootstrap_self_admin(_admin(name))
            return "ok"
        except RoleRegistryMutationError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["a", "b"]))

    assert results.count("ok") == 1
    assert any("ALREADY_INITIALIZED" in result for result in results)


def test_upsert_remove_and_last_admin_projection(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")
    actor = _admin("root")
    store.bootstrap_self_admin(actor)
    manager_digest = sha256_text("manager")

    manager, _audit = store.upsert_member(actor=actor, target_admin_id_digest=manager_digest, role="manager")
    assert manager.role == "manager"
    assert store.lookup_active(manager_digest).role == "manager"

    with pytest.raises(RoleRegistryMutationError, match="LAST_ADMIN"):
        store.upsert_member(actor=actor, target_admin_id_digest=actor.admin_id_digest, role="manager")
    with pytest.raises(RoleRegistryMutationError, match="LAST_ADMIN"):
        store.remove_member(actor=actor, target_admin_id_digest=actor.admin_id_digest)

    second_admin_digest = sha256_text("second-admin")
    store.upsert_member(actor=actor, target_admin_id_digest=second_admin_digest, role="admin")
    removed, _ = store.remove_member(actor=actor, target_admin_id_digest=actor.admin_id_digest)
    assert removed.status == "REMOVED"
    assert store.lookup_active(actor.admin_id_digest) is None
    assert store.status_summary()["active_admin_count"] == 1


def test_index_and_audit_do_not_persist_raw_identity(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")
    store.bootstrap_self_admin(_admin("raw-zero-admin"))
    text = store.index_path.read_text(encoding="utf-8")
    audit_text = (tmp_path / "registry" / "role_registry_audit_log.jsonl").read_text(encoding="utf-8")
    encoded = json.dumps({"index": text, "audit": audit_text}, ensure_ascii=False)

    assert "raw-zero-admin" not in encoded
    assert "@" not in encoded
    assert "Bearer" not in encoded


def test_populated_registry_blocks_when_audit_files_are_missing(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")
    actor = _admin("audit-required-admin")
    store.bootstrap_self_admin(actor)

    (tmp_path / "registry" / "role_registry_audit_log.jsonl").unlink()
    (tmp_path / "registry" / "role_registry_audit_head.json").unlink()

    with pytest.raises(RoleRegistryLoadError):
        store.lookup_active(actor.admin_id_digest)
    with pytest.raises(RoleRegistryLoadError):
        store.status_summary()
    with pytest.raises(RoleRegistryLoadError):
        store.upsert_member(actor=actor, target_admin_id_digest=sha256_text("next-admin"), role="admin")


def test_malformed_vault_entry_is_wrapped_as_registry_load_failure(tmp_path):
    store = RoleRegistryStore(root=tmp_path / "registry")
    actor = _admin("malformed-vault-admin")
    store.bootstrap_self_admin(actor)
    data = json.loads(store.index_path.read_text(encoding="utf-8"))
    index_entry = RoleRegistryIndexEntry(**data["members"][actor.admin_id_digest])
    value = store.vault.decrypt_json(index_entry.entry_ref, aad=index_entry.entry_digest)
    value["registered_by_digest"] = "not-a-digest"
    item_id = index_entry.entry_ref.rsplit("/", 1)[-1]
    store.vault.encrypt_json("role_registry", item_id, value, aad=index_entry.entry_digest)

    with pytest.raises(RoleRegistryLoadError):
        store.lookup_active(actor.admin_id_digest)
