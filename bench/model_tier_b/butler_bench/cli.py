from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifact_scanner import scan_artifact_tree
from .attestation import load_trust_policy, replay_sigstore_verification
from .canonical import canonical_sha256, read_json_closed, write_canonical_json
from .errors import ExitCode, FailClass, GateError
from .model_manifest import build_model_manifest, verify_model_manifest
from .policy import load_approved_policy
from .preflight import validate_m3_gate_receipts
from .product_bridge import validate_product_module
from .schedule import build_schedule, verify_fixture_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="butler-model-tier-b", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    policy = sub.add_parser("policy-check", allow_abbrev=False)
    policy.add_argument("--policy", type=Path, required=True); policy.add_argument("--expected-sha256", required=True)
    trust = sub.add_parser("trust-check", allow_abbrev=False)
    trust.add_argument("--trust-policy", type=Path, required=True); trust.add_argument("--expected-sha256", required=True)
    manifest = sub.add_parser("model-manifest", allow_abbrev=False)
    manifest.add_argument("--root", type=Path, required=True); manifest.add_argument("--metadata-sha256", required=True)
    manifest.add_argument("--variant-id", required=True); manifest.add_argument("--output", type=Path, required=True)
    verify_model = sub.add_parser("model-verify", allow_abbrev=False)
    verify_model.add_argument("--root", type=Path, required=True); verify_model.add_argument("--manifest", type=Path, required=True)
    schedule = sub.add_parser("schedule-build", allow_abbrev=False)
    schedule.add_argument("--policy", type=Path, required=True); schedule.add_argument("--policy-sha256", required=True)
    schedule.add_argument("--fixture-manifest", type=Path, required=True); schedule.add_argument("--output", type=Path, required=True)
    scan = sub.add_parser("artifact-scan", allow_abbrev=False)
    scan.add_argument("--root", type=Path, required=True); scan.add_argument("--manifest", type=Path, required=True)
    scan.add_argument("--scanner-policy", type=Path, required=True)
    product = sub.add_parser("product-preflight", allow_abbrev=False)
    product.add_argument("--module", required=True); product.add_argument("--product-root", type=Path, required=True)
    product.add_argument("--module-sha256", required=True); product.add_argument("--commit-oid", required=True)
    m3 = sub.add_parser("m3-gate-check", allow_abbrev=False)
    m3.add_argument("--receipts-dir", type=Path, required=True); m3.add_argument("--expected-subjects", type=Path, required=True)
    m3.add_argument("--expected-subjects-sha256", required=True)
    replay = sub.add_parser("attestation-replay", allow_abbrev=False)
    replay.add_argument("--cosign", type=Path, required=True); replay.add_argument("--cosign-sha256", required=True)
    replay.add_argument("--payload", type=Path, required=True); replay.add_argument("--bundle", type=Path, required=True)
    replay.add_argument("--statement", type=Path, required=True); replay.add_argument("--trust-policy", type=Path, required=True)
    replay.add_argument("--trust-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "policy-check":
            result = load_approved_policy(args.policy, expected_sha256=args.expected_sha256)
            safe_print({"status": "PASS", "policy_sha256": result.canonical_sha256})
        elif args.command == "trust-check":
            result = load_trust_policy(args.trust_policy, expected_sha256=args.expected_sha256)
            safe_print({"status": "PASS", "trust_policy_sha256": result.digest})
        elif args.command == "model-manifest":
            value = build_model_manifest(args.root, metadata_sha256=args.metadata_sha256, variant_id=args.variant_id)
            write_canonical_json(args.output, value); safe_print({"status": "PASS", "model_manifest_sha256": value["model_manifest_sha256"]})
        elif args.command == "model-verify":
            safe_print({"status": "PASS", "model_manifest_sha256": verify_model_manifest(args.root, read_json_closed(args.manifest))})
        elif args.command == "schedule-build":
            receipt = load_approved_policy(args.policy, expected_sha256=args.policy_sha256)
            policy = dict(receipt.normalized); policy["_payload_sha256"] = receipt.canonical_sha256
            fixtures = read_json_closed(args.fixture_manifest); verify_fixture_manifest(fixtures)
            value = build_schedule(policy, fixtures); write_canonical_json(args.output, value)
            safe_print({"status": "PASS", "schedule_sha256": value["schedule_sha256"]})
        elif args.command == "artifact-scan":
            safe_print(scan_artifact_tree(args.root, read_json_closed(args.manifest), read_json_closed(args.scanner_policy)))
        elif args.command == "product-preflight":
            value = validate_product_module(args.module, approved_product_root=args.product_root, expected_module_sha256=args.module_sha256, expected_commit_oid=args.commit_oid)
            safe_print({"status": "PASS", **value})
        elif args.command == "m3-gate-check":
            subjects = read_json_closed(args.expected_subjects)
            if canonical_sha256(subjects) != args.expected_subjects_sha256:
                raise GateError(FailClass.PREFLIGHT, "EXPECTED_SUBJECTS_DIGEST", exit_code=ExitCode.DIGEST)
            receipts = [read_json_closed(path) for path in sorted(args.receipts_dir.glob("*.json"))]
            safe_print({"status": "PASS", **validate_m3_gate_receipts(receipts, expected_subjects=subjects)})
        elif args.command == "attestation-replay":
            trust_receipt = load_trust_policy(args.trust_policy, expected_sha256=args.trust_sha256)
            result = replay_sigstore_verification(
                cosign_binary=args.cosign, expected_cosign_sha256=args.cosign_sha256,
                payload=args.payload, bundle=args.bundle, statement=args.statement, policy=trust_receipt,
            )
            safe_print({"status": "PASS", **result})
        return int(ExitCode.PASS)
    except GateError as exc:
        safe_print(exc.as_safe_dict()); return int(exc.exit_code)
    except Exception:
        error = GateError(FailClass.INTERNAL_VERIFIER_ERROR, "UNHANDLED", exit_code=ExitCode.INTERNAL)
        safe_print(error.as_safe_dict()); return int(error.exit_code)


def safe_print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
