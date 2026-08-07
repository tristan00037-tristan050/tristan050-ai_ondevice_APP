#!/usr/bin/env python3
"""Build a deterministic approval-input ZIP from already verified protected evidence."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_closure import ROLE_MEDIA_TYPES  # noqa: E402
from scripts.ci.helper1_product_approval_bundle import load_bundle  # noqa: E402

INVENTORY_NAME = "APPROVAL_INPUT_INVENTORY.v2.json"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def build_package(
    source_root: Path,
    *,
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> bytes:
    files = load_bundle(
        source_root,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
        producer_run=producer_run,
    )
    inventory: dict[str, object] = {}
    for name, raw in sorted(files.items()):
        role = None
        media_type = "application/json"
        if name.startswith("objects/"):
            media_type = "application/octet-stream"
        elif name.startswith("approval/"):
            role = name.rsplit("/", 1)[1].rsplit(".", 2)[0]
            media_type = (
                ROLE_MEDIA_TYPES[role]
                if name.endswith(".payload.json")
                else "application/vnd.butler.helper1.evidence-envelope+json;v=1"
            )
        inventory[name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": media_type,
            "role": role,
        }
    payload = dict(files)
    payload[INVENTORY_NAME] = _canonical(
        {
            "schema_version": "butler.helper1.approval-input-inventory.v2",
            "files": inventory,
        }
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100600 << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--subject-tree", required=True)
    parser.add_argument("--producer-run", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = build_package(
            args.source_root,
            subject_commit=args.subject_commit,
            subject_tree=args.subject_tree,
            producer_run=args.producer_run,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
    except Exception:
        print("HELPER1_APPROVAL_INPUT_PACKAGE_OK=0")
        print("ERROR_CODE=INVENTORY_INCOMPLETE")
        return 1
    print("HELPER1_APPROVAL_INPUT_PACKAGE_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
