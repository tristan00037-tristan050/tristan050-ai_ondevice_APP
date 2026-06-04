from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .actual_fail_class import (
    BLOCK_HELPER_ASSET_DRIFT,
    BLOCK_HELPER_REAL_USE_GUARD_PENDING,
    PARTIAL_HELPER_STACK_UNSUPPORTED,
)

HELPER_EXPECTED_SHA = {
    "helper3_format": "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0",
    "helper4_grounding": "b7b1af0ebfddc17bf9164ab124f8b598d97954f1a9fa067abf1e68f020c95e40",
    "helper7_table_figure": "8b03454967a9f16d12e408ea85ab3b27efe5a3e053c8150480cb70646fa4dfb0",
    "helper8_company_style": "7d4f8311ab427e4b609e2d22d7aff6e89a19085eaaa788677c7ed24d789d6d52",
}


@dataclass(frozen=True)
class HelperComponentGuardVerdict:
    allowed: bool
    fail_class: str | None
    component_use_allowed_count: int
    helper_count: int
    helper_stack_supported: bool
    helper_digests: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_helper_component_use_guard(guard: dict[str, Any] | None) -> HelperComponentGuardVerdict:
    if not isinstance(guard, dict):
        return HelperComponentGuardVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, 0, 0, False, {})
    helpers = guard.get("helpers")
    if not isinstance(helpers, list):
        return HelperComponentGuardVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, 0, 0, False, {})
    by_name = {row.get("asset_name"): row for row in helpers if isinstance(row, dict)}
    if set(by_name) != set(HELPER_EXPECTED_SHA):
        return HelperComponentGuardVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, 0, len(by_name), False, {})
    digests: dict[str, str] = {}
    allowed_count = 0
    for name, expected in HELPER_EXPECTED_SHA.items():
        row = by_name[name]
        digest = row.get("sha256_full")
        digests[name] = str(digest)
        if digest != expected:
            return HelperComponentGuardVerdict(False, BLOCK_HELPER_ASSET_DRIFT, allowed_count, len(by_name), False, digests)
        if row.get("component_use_allowed") is not True:
            return HelperComponentGuardVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, allowed_count, len(by_name), False, digests)
        allowed_count += 1
    stack_supported = guard.get("helper_stacking_supported") is True
    if not stack_supported:
        return HelperComponentGuardVerdict(False, PARTIAL_HELPER_STACK_UNSUPPORTED, allowed_count, len(by_name), False, digests)
    return HelperComponentGuardVerdict(True, None, allowed_count, len(by_name), True, digests)


def build_example_component_use_guard(*, allow: bool = False, stack_supported: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "box3.helper_component_use_guard.v1",
        "helper_stacking_supported": stack_supported,
        "helpers": [
            {
                "asset_name": name,
                "sha256_full": digest,
                "component_use_allowed": allow,
                "production_claim_allowed": False,
                "evidence_digest": "sha256:" + digest,
            }
            for name, digest in HELPER_EXPECTED_SHA.items()
        ],
    }
