from __future__ import annotations

import pytest

from butler_pc_core.assets.service import unavailable_status_projection

pytestmark = pytest.mark.no_sidecar_token


def test_unconfigured_state_propagates_to_all_release_consumers() -> None:
    status = unavailable_status_projection()
    assert status == {
        "schema_version": 2,
        "overall_state": "UNAVAILABLE",
        "groups": [],
        "byte_safety_verified": False,
        "origin_verified": False,
        "trust_root_state": "UNCONFIGURED",
        "signature_state": "MISSING",
        "provenance_state": "UNVERIFIED",
        "release_ready": False,
        "external_handoff_allowed": 0,
        "auto_update_allowed": 0,
        "operation_scope": "INTERNAL_OWNER_ONLY",
    }
