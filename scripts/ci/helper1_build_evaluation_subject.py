#!/usr/bin/env python3
"""Derive one immutable evaluation subject from native product identities."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.composition import (  # noqa: E402
    load_native_ablation_assembly,
    load_native_product_assembly,
)
from butler_pc_core.helper1.contracts import (  # noqa: E402
    EvaluationRunSubjectV2,
    canonical_json,
    sha256_bytes,
)
from butler_pc_core.helper1.evaluation import (  # noqa: E402
    evaluation_query_manifest_sha256,
    evaluation_query_v2_from_mapping,
)
from butler_pc_core.helper1.pipeline import render_rag_prompt  # noqa: E402
from butler_pc_core.helper1.quality_evidence import DECODING_POLICY_V1  # noqa: E402


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if type(value) is not dict:
        raise ValueError
    return value


def _queries(path: Path):
    rows = []
    for line in path.read_bytes().splitlines():
        value = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError
        rows.append(evaluation_query_v2_from_mapping(value))
    if not rows:
        raise ValueError
    return tuple(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-policy", required=True, type=Path)
    parser.add_argument("--threshold-policy", required=True, type=Path)
    parser.add_argument("--threshold-approval-envelope", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        queries = _queries(args.queries)
        corpus = _object(args.corpus_manifest)
        retrieval_policy = _object(args.retrieval_policy)
        threshold_policy = _object(args.threshold_policy)
        threshold_envelope = args.threshold_approval_envelope.read_bytes()
        normal = load_native_product_assembly()
        if normal is None:
            raise ValueError
        ablation = load_native_ablation_assembly(normal.pipeline.index.manifest.digest)
        if ablation is None:
            raise ValueError
        subject = EvaluationRunSubjectV2(
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            source_commit=args.source_commit,
            source_tree=args.source_tree,
            query_manifest_sha256=evaluation_query_manifest_sha256(queries),
            corpus_manifest_sha256=sha256_bytes(canonical_json(corpus)),
            retrieval_policy_sha256=sha256_bytes(canonical_json(retrieval_policy)),
            threshold_policy_sha256=sha256_bytes(canonical_json(threshold_policy)),
            threshold_approval_receipt_sha256=hashlib.sha256(threshold_envelope).hexdigest(),
            encoder_space_sha256=normal.pipeline.embedder.identity.digest,
            normal_index_manifest_sha256=normal.pipeline.index.manifest.digest,
            ablation_index_manifest_sha256=ablation.pipeline.index.manifest.digest,
            generator_identity_sha256=normal.pipeline.generator.identity_sha256,
            prompt_template_sha256=sha256_bytes(render_rag_prompt.__code__.co_code),
            decoding_policy_sha256=sha256_bytes(canonical_json(DECODING_POLICY_V1)),
            seed=0,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(subject.to_dict()) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        print("HELPER1_EVALUATION_SUBJECT_OK=0")
        print("ERROR_CODE=EVALUATION_INPUT_UNAVAILABLE")
        return 1
    print("HELPER1_EVALUATION_SUBJECT_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
