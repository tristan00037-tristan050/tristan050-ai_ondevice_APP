#!/usr/bin/env python3
"""Verify post-build AC-23 mutation evidence without trusting summaries."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from strict_json import (
    StrictJsonError,
    require_exact_dict_keys,
    require_git_oid,
    strict_json_file,
)
from verify_candidate_artifact_identity import (
    MANIFEST_KEYS,
    VerificationError,
    load_evidence_policy,
    verify_mutation_results,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(results: Path, policy_path: Path, package: Path) -> None:
    results = results.resolve()
    stem = results.with_suffix("")
    paths = {
        "mutation/mutation_results_v3.json": results,
        "mutation/pytest_mutation.stdout.bin": stem.with_suffix(".stdout.bin"),
        "mutation/pytest_mutation.stderr.bin": stem.with_suffix(".stderr.bin"),
        "mutation/pytest_mutation.xml": stem.with_suffix(".xml"),
        "mutation/canonical.json": stem.with_suffix(".canonical.json"),
    }
    if not all(path.is_file() and not path.is_symlink() for path in paths.values()):
        raise VerificationError("E_EVIDENCE_INVENTORY")
    policy = load_evidence_policy(policy_path.resolve().read_bytes())
    package = package.resolve()
    identity_path = package / "IDENTITY" / "candidate_artifact_identity.json"
    identity = strict_json_file(identity_path, max_bytes=1 << 20, require_canonical=True)
    require_exact_dict_keys(identity, MANIFEST_KEYS)
    require_git_oid(identity["head_commit"])
    require_git_oid(identity["head_tree"])
    subject = {
        "subject_checksum_sha256": _sha256(package / "SHA256SUMS.txt"),
        "subject_identity_sha256": _sha256(identity_path),
        "subject_head_commit": identity["head_commit"],
        "subject_head_tree": identity["head_tree"],
    }
    verify_mutation_results(
        {relative: path.read_bytes() for relative, path in paths.items()},
        policy,
        expected_subject=subject,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("evidence_policy_v3.json"),
    )
    args = parser.parse_args()
    try:
        verify(args.results, args.policy, args.package)
    except (VerificationError, StrictJsonError) as error:
        code = error.code if isinstance(error, VerificationError) else "E_EVIDENCE_SCHEMA"
        print(
            '{"error_code":"' + code + '","mutation_evidence_pass":0}',
            file=__import__("sys").stderr,
        )
        return 1
    except Exception:
        print(
            '{"error_code":"E_EVIDENCE_SCHEMA","mutation_evidence_pass":0}',
            file=__import__("sys").stderr,
        )
        return 1
    print('{"error_code":"","mutation_evidence_pass":1}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
