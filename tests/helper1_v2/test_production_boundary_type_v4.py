from __future__ import annotations

import base64
import hashlib
import time
import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.contracts import canonical_json
from butler_pc_core.helper1.execution import NativeExecutionAuthority
from butler_pc_core.helper1.ingestion import ApprovedFolderIngestor, IngestionError
from butler_pc_core.helper1.service import Helper1Service, Helper1ServiceError


class SelfReportedProductionParser:
    is_production_parser = True
    policy_sha256 = "0" * 64

    def parse(self, data: bytes, extension: str) -> str:
        del data, extension
        return "forged"


class SelfReportedProductionKeyProvider:
    is_production_provider = True

    def key(self, workspace_id: str) -> tuple[str, bytes]:
        del workspace_id
        return "forged", b"x" * 32


def _authority(
    *, workspace_id: str, generation_id: str, artifact_digest: str
) -> NativeExecutionAuthority:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(public_key).hexdigest()
    now = int(time.time())
    unsigned = {
        "schema_version": "butler.helper1.activation-grant.v3",
        "key_id": key_id,
        "subject_commit": "a" * 40,
        "subject_tree": "b" * 40,
        "workspace_id": workspace_id,
        "generation_id": generation_id,
        "actions": ["ask", "search"],
        "artifact_digests": [artifact_digest],
        "not_before_epoch_s": now - 1,
        "expires_at_epoch_s": now + 60,
        "grant_nonce_sha256": "c" * 64,
    }
    grant = {
        **unsigned,
        "signature_b64": base64.b64encode(
            private_key.sign(canonical_json(unsigned))
        ).decode("ascii"),
    }
    return NativeExecutionAuthority(
        public_key_bytes=public_key,
        expected_public_key_sha256=key_id,
        signed_activation_grant=grant,
        native_signer=lambda _challenge: {},
        clock=lambda: now,
    )


def test_parser_self_report_cannot_cross_product_boundary(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    folder_fd = __import__("os").open(root, __import__("os").O_RDONLY)
    try:
        with pytest.raises(IngestionError, match="PARSER_PRODUCTION_BOUNDARY_REQUIRED"):
            ApprovedFolderIngestor(
                workspace_id=str(uuid.uuid4()),
                folder_fd=folder_fd,
                workspace_key=b"k" * 32,
                parser=SelfReportedProductionParser(),
            )
    finally:
        __import__("os").close(folder_fd)


def test_pipeline_and_key_provider_self_reports_cannot_register():
    workspace_id = str(uuid.uuid4())
    fake_pipeline = SimpleNamespace(
        index=SimpleNamespace(manifest=SimpleNamespace(workspace_id=workspace_id)),
        effect_authority=SimpleNamespace(
            key_provider=SelfReportedProductionKeyProvider()
        ),
        retriever=SimpleNamespace(policy=SimpleNamespace(is_calibrated=True)),
        measurement_authority=SimpleNamespace(is_production_observer=True),
    )
    fake_execution = SimpleNamespace(
        is_production_authority=True,
        grant=SimpleNamespace(workspace_id=workspace_id, generation_id=str(uuid.uuid4())),
    )
    with pytest.raises(Helper1ServiceError, match="PRODUCTION_PIPELINE_TYPE_REQUIRED"):
        Helper1Service().register_native_pipeline(
            workspace_id,
            fake_pipeline,
            execution_authority=fake_execution,
            session_digest="0" * 64,
        )


def test_activation_grant_must_cover_exact_index_manifest_digest():
    workspace_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    approved = "d" * 64
    authority = _authority(
        workspace_id=workspace_id,
        generation_id=generation_id,
        artifact_digest=approved,
    )
    assert Helper1Service._activation_grant_covers(
        authority,
        workspace_id=workspace_id,
        generation_id=generation_id,
        manifest_sha256=approved,
    )
    assert not Helper1Service._activation_grant_covers(
        authority,
        workspace_id=workspace_id,
        generation_id=generation_id,
        manifest_sha256="e" * 64,
    )
