#!/usr/bin/env python3
"""Verify the installed FirstScreen trust chain with in-process Ed25519.

The bootstrap file is a consumer-installed trust input.  Release bundles must
not contain or select it.  This compatibility entry point replaces the v2.3
OpenSSH subprocess verifier; all cryptographic policy lives in
``butler_pc_core.firstscreen_trust``.
"""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_trust import (
    BootstrapRoot,
    strict_json_loads,
    verify_revocations,
    verify_risk_decision,
    verify_root_chain,
)


MAX_INPUT_BYTES = 256 * 1024


def _read_regular(path: Path) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise RuntimeError("ARTIFACT_TYPE_INVALID")
    if metadata.st_size <= 0 or metadata.st_size > MAX_INPUT_BYTES:
        raise RuntimeError("ARTIFACT_SIZE_INVALID")
    return path.read_bytes()


def _bootstrap(path: Path) -> BootstrapRoot:
    value = strict_json_loads(_read_regular(path), maximum=16 * 1024)
    expected = {
        "schema_version",
        "policy_digest",
        "minimum_root_version",
        "minimum_revocation_version",
        "authority",
    }
    if set(value) != expected or value["schema_version"] != "butler.firstscreen.bootstrap.v1":
        raise RuntimeError("BOOTSTRAP_SCHEMA_INVALID")
    if value["authority"] not in {"SIGNED_APP_BINARY", "PROTECTED_CI", "OFFLINE_CONSUMER"}:
        raise RuntimeError("BOOTSTRAP_AUTHORITY_INVALID")
    return BootstrapRoot(
        policy_digest=value["policy_digest"],
        minimum_root_version=value["minimum_root_version"],
        minimum_revocation_version=value["minimum_revocation_version"],
    )


def verify_installed_policy(*, bootstrap: Path, root: Path, revocations: Path, decision: Path) -> None:
    anchor = _bootstrap(bootstrap)
    verified_root = verify_root_chain(anchor, _read_regular(root))
    verified_revocations = verify_revocations(
        verified_root,
        _read_regular(revocations),
        bootstrap=anchor,
    )
    verify_risk_decision(verified_root, verified_revocations, _read_regular(decision))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--revocations", required=True, type=Path)
    parser.add_argument("--decision", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        verify_installed_policy(
            bootstrap=arguments.bootstrap.resolve(),
            root=arguments.root.resolve(),
            revocations=arguments.revocations.resolve(),
            decision=arguments.decision.resolve(),
        )
    except Exception:
        print("STORAGE_RISK_ACCEPTANCE_OK=0 ERROR_CODE=STORAGE_RISK_ACCEPTANCE_INVALID")
        return 1
    print("STORAGE_RISK_ACCEPTANCE_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
