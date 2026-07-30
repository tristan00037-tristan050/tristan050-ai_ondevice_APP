from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping

from .contracts import AssetManifest, VerificationReceipt, VerifiedAsset


def issue_group_receipt(
    *,
    run_id: str,
    build_id: str,
    release_profile: str,
    manifest_set_sha256: str | None,
    manifest: AssetManifest,
    assets: Mapping[str, VerifiedAsset],
    verifier_version: str,
) -> VerificationReceipt:
    return VerificationReceipt(
        schema_version=1,
        run_id=run_id,
        build_id=build_id,
        release_profile=release_profile,
        asset_group=manifest.asset_group,
        group_version=manifest.group_version,
        manifest_digest=manifest.digest,
        manifest_set_sha256=manifest_set_sha256
        or hashlib.sha256(b"").hexdigest(),
        roles=tuple(sorted(assets)),
        identity_tokens=tuple(
            assets[role].identity_token for role in sorted(assets)
        ),
        verifier_version=verifier_version,
        verified_monotonic_ns=time.monotonic_ns(),
    )
