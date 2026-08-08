"""Validate the externally written artifact-chain proof without repository writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ops.write_external_json_atomic import ExternalWriteError, read_external_regular


REQUIRED_TOP = (
    "proof_version", "bundle_id", "verified_at_utc", "git_sha", "environment_id",
    "verifier_results", "manifest_digest_sha256", "sbom_digest_sha256",
    "provenance_digest_sha256", "result_fingerprint_sha256",
)
REQUIRED_RESULTS = (
    "tuf_min_signing_chain", "sbom_from_artifacts", "manifest_bind",
    "bundle_integrity", "provenance_link", "verifier_chain",
)
FORBIDDEN = frozenset({"raw", "origin", "content", "body", "full_output", "stdout", "stderr"})


class ArtifactChainError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _walk(value, depth: int = 0) -> None:
    if depth > 5:
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_DEPTH_EXCEEDED")
    if isinstance(value, str) and len(value) > 500:
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_STRING_TOO_LONG")
    if isinstance(value, list):
        for child in value:
            _walk(child, depth + 1)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN:
                raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_META_ONLY_VIOLATION")
            _walk(child, depth + 1)


def validate(raw: bytes) -> None:
    try:
        document = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_JSON_INVALID") from exc
    if not isinstance(document, dict):
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_JSON_INVALID")
    if any(key not in document for key in REQUIRED_TOP):
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_KEY_MISSING")
    if document["proof_version"] != 2:
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_VERSION_INVALID")
    results = document.get("verifier_results")
    if not isinstance(results, dict) or any(results.get(key) != "ok" for key in REQUIRED_RESULTS):
        raise ArtifactChainError("ARTIFACT_CHAIN_PROOF_RESULT_INVALID")
    _walk(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    try:
        raw = read_external_regular(
            evidence_root=Path(args.evidence_root),
            path=Path(args.path),
            max_bytes=16 * 1024 * 1024,
        )
        validate(raw)
    except (ExternalWriteError, ArtifactChainError) as exc:
        print(f"ERROR_CODE={exc.code}")
        return 1
    print("ARTIFACT_CHAIN_PROOF_V2_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
