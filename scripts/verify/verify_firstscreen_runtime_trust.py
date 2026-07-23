#!/usr/bin/env python3
"""Verify release/runtime trust inputs and emit the canonical native/UI receipt."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_runtime_trust import (
    InMemoryRuntimeTrustStateStore,
    read_external_root_pin,
    verify_and_advance_runtime_trust,
)


def _read(path: Path, maximum: int = 1024 * 1024 * 1024) -> bytes:
    resolved = path.resolve(strict=True)
    metadata = resolved.lstat()
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not 0 < metadata.st_size <= maximum:
        raise RuntimeError("RUNTIME_TRUST_INPUT_INVALID")
    return resolved.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--revocations", required=True, type=Path)
    parser.add_argument("--risk-decision", required=True, type=Path)
    parser.add_argument("--build-context", required=True, type=Path)
    parser.add_argument("--release-subjects", required=True, type=Path)
    parser.add_argument("--external-root-pin", required=True, type=Path)
    parser.add_argument("--application-root", required=True, type=Path)
    for name in ("source-archive", "web-dist", "macos-artifact", "sbom"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        receipt = verify_and_advance_runtime_trust(
            root_bytes=_read(arguments.root, 256 * 1024),
            revocation_bytes=_read(arguments.revocations, 256 * 1024),
            decision_bytes=_read(arguments.risk_decision, 256 * 1024),
            build_context_bytes=_read(arguments.build_context, 64 * 1024),
            release_subjects_bytes=_read(arguments.release_subjects, 256 * 1024),
            artifacts={
                "source_archive": _read(arguments.source_archive),
                "web_dist_archive": _read(arguments.web_dist),
                "macos_artifact": _read(arguments.macos_artifact),
                "sbom": _read(arguments.sbom),
            },
            external_pin_bytes=read_external_root_pin(
                arguments.external_root_pin,
                application_root=arguments.application_root,
            ),
            store=InMemoryRuntimeTrustStateStore(),
        )
    except Exception:
        print("RUNTIME_TRUST_VERIFY_OK=0 ERROR_CODE=RUNTIME_TRUST_INVALID")
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
