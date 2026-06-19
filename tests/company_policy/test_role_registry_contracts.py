from __future__ import annotations

import pytest

from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.company_policy.role_registry_contracts import (
    RoleRegistryContractError,
    compute_role_registry_entry_digest,
    make_role_registry_entry,
    make_role_registry_index_entry,
)


def test_entry_digest_and_index_are_digest_only():
    entry = make_role_registry_entry(
        target_admin_id_digest=sha256_text("target-admin"),
        role="admin",
        status="ACTIVE",
        registered_by_digest=sha256_text("actor-admin"),
        updated_by_digest=sha256_text("actor-admin"),
        version=1,
    )
    assert entry.entry_digest == compute_role_registry_entry_digest(entry.unsigned_dict())

    index_entry = make_role_registry_index_entry(entry=entry, entry_ref="local-vault://role_registry/entry-test")
    payload = index_entry.to_dict()
    assert payload["target_admin_id_digest"].startswith("sha256:")
    assert payload["role"] == "admin"
    assert payload["raw_text_logged"] is False
    assert payload["external_send_zero"] is True


def test_entry_rejects_invalid_digest_role_and_status():
    with pytest.raises(Exception):
        make_role_registry_entry(
            target_admin_id_digest="sha256:bad",
            role="admin",
            status="ACTIVE",
            registered_by_digest=sha256_text("actor"),
            updated_by_digest=sha256_text("actor"),
            version=1,
        )
    with pytest.raises(RoleRegistryContractError, match="ROLE_REGISTRY_ROLE_INVALID"):
        make_role_registry_entry(
            target_admin_id_digest=sha256_text("target"),
            role="owner",
            status="ACTIVE",
            registered_by_digest=sha256_text("actor"),
            updated_by_digest=sha256_text("actor"),
            version=1,
        )
    with pytest.raises(RoleRegistryContractError, match="ROLE_REGISTRY_STATUS_INVALID"):
        make_role_registry_entry(
            target_admin_id_digest=sha256_text("target"),
            role="admin",
            status="DELETED",
            registered_by_digest=sha256_text("actor"),
            updated_by_digest=sha256_text("actor"),
            version=1,
        )
