from __future__ import annotations

import hashlib
import json
import os

from butler_pc_core.helper1.asset_lease import VerifiedAssetLease
from butler_pc_core.helper1.contracts import canonical_json, sha256_bytes
from butler_pc_core.helper1.security import ClosureFile, VerifiedAssetClosure


def test_lease_consumes_private_inode_after_source_overwrite(tmp_path):
    source = tmp_path / "model.gguf"
    original = b"verified-model-bytes"
    source.write_bytes(original)
    record = ClosureFile("model.gguf", len(original), hashlib.sha256(original).hexdigest())
    manifest_digest = sha256_bytes(
        canonical_json(
            {
                "schema_version": "butler.asset-closure.v1",
                "files": {
                    "model.gguf": {"bytes": record.bytes, "sha256": record.sha256}
                },
            }
        )
    )
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        source_mapping = {"model.gguf": record}
        closure = VerifiedAssetClosure(root_fd, source_mapping, manifest_digest)
        closure.verify_all()
        source_mapping["forged.gguf"] = record
        with VerifiedAssetLease.create(closure, "model.gguf") as lease:
            before = lease.measure()
            source.write_bytes(b"attacker-overwrite")
            after = lease.measure()
            receipt = lease.consumption_receipt(before, after)
            duplicate = lease.duplicate_fd()
            try:
                assert os.read(duplicate, len(original)) == original
            finally:
                os.close(duplicate)
            assert receipt.sha256_before == hashlib.sha256(original).hexdigest()
            assert receipt.sha256_after == receipt.sha256_before
            assert receipt.descriptor_only is True
        assert tuple(closure.files) == ("model.gguf",)
        assert json.dumps(receipt.to_dict(), sort_keys=True)
    finally:
        os.close(root_fd)
