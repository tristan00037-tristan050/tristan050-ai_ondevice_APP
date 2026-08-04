from __future__ import annotations

import json
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

from butler_pc_core.helper1.contracts import (
    AnswerKind,
    AnswerResult,
    ArtifactRecord,
    AssetIdentity,
    EncoderIdentity,
    IndexManifest,
)
from butler_pc_core.helper1.release import ORDERED_GATES, ReleaseReceipt

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts" / "helper1"
DIGEST = "a" * 64


def _schema(name: str):
    value = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def _encoder():
    return EncoderIdentity(
        asset=AssetIdentity(
            role="helper1_embed",
            model_id="BAAI/bge-m3",
            upstream_revision="5617a9f61b028005a4858fdac845db406aefb181",
            closure_manifest_sha256=DIGEST,
            runtime_name="runtime",
            runtime_version="pinned-1",
            runtime_binary_sha256=DIGEST,
            tokenizer_sha256=DIGEST,
        ),
        pooling="cls",
        normalize=True,
        dimension=1024,
        max_length=8192,
        truncation_policy="reject",
        document_prefix_sha256=DIGEST,
        query_prefix_sha256=DIGEST,
    )


def test_answer_schema_accepts_typed_asset_refusal():
    workspace_id = str(uuid.uuid4())
    value = AnswerResult(
        kind=AnswerKind.REFUSED_ASSET_MISSING,
        request_id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        generation_id=None,
        answer=None,
        reason_code="HELPER1_RUNTIME_NOT_BOOTSTRAPPED",
        model_identity_sha256=None,
        index_manifest_sha256=None,
    ).to_public_dict()
    _schema("answer-result-v2.schema.json").validate(value)


def test_index_manifest_schema_accepts_canonical_manifest():
    manifest = IndexManifest(
        workspace_id=str(uuid.uuid4()),
        generation_id=str(uuid.uuid4()),
        encoder=_encoder(),
        lexical_tokenizer_sha256=DIGEST,
        chunker_policy_sha256=DIGEST,
        parser_isolation_policy_sha256=DIGEST,
        document_set_hmac_sha256=DIGEST,
        policy_sha256=DIGEST,
        chunk_count=1,
        embedding_rows=1,
        embedding_dimension=1024,
        lexical_term_count=1,
        artifacts={
            "chunks": ArtifactRecord("chunks.enc", 1, DIGEST),
            "embeddings": ArtifactRecord("embeddings.enc", 1, DIGEST),
            "lexical_index": ArtifactRecord("lexical.enc", 1, DIGEST),
        },
    )
    _schema("index-manifest-v2.schema.json").validate(manifest.to_dict())


def test_release_receipt_schema_accepts_exact_gate_order():
    receipt = ReleaseReceipt(
        request_id=str(uuid.uuid4()),
        workspace_id=str(uuid.uuid4()),
        generation_id=str(uuid.uuid4()),
        policy_sha256=DIGEST,
        gate_bundle_sha256=DIGEST,
        ordered_trace_root=DIGEST,
        authority_key_id="test-key",
        signature="A" * 86,
        terminal_count=1,
        ordered_gates=ORDERED_GATES,
    )
    _schema("release-receipt-v2.schema.json").validate(receipt.to_dict())


def test_attack_scenario_inventory_is_nonempty_and_unique():
    value = json.loads(
        (CONTRACTS / "attack-scenarios-v2.json").read_text(encoding="utf-8")
    )
    scenarios = value["scenarios"]
    identifiers = [scenario["id"] for scenario in scenarios]
    assert len(identifiers) >= 16
    assert len(identifiers) == len(set(identifiers))
