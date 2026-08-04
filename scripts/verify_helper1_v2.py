#!/usr/bin/env python3
"""Untrusted-tree Helper1 preflight; it can never publish CODE_PASS=1.

The authoritative product verdict is emitted only by
``scripts/ci/helper1_trusted_verifier.py`` running from the protected default
branch through ``workflow_run``. Evidence producers and pull requests cannot
select a verifier, key, policy manifest, or expected hash here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = ROOT / "butler_pc_core" / "helper1"
ROUTE = ROOT / "butler_pc_core" / "sidecar" / "routes" / "helper1_search.py"
CONTRACT_ROOT = ROOT / "contracts" / "helper1"
TRUSTED_VERIFIER = ROOT / "scripts" / "ci" / "helper1_trusted_verifier.py"
TRUSTED_POLICY = CONTRACT_ROOT / "trusted-verifier-policy-v1.json"
TRUSTED_COMPONENTS = {
    "scripts/ci/helper1_trusted_verifier.py": TRUSTED_VERIFIER,
    "scripts/ci/helper1_subject_binding.py": ROOT / "scripts/ci/helper1_subject_binding.py",
    "scripts/ci/helper1_evidence_semantics.py": ROOT / "scripts/ci/helper1_evidence_semantics.py",
    "scripts/ci/helper1_postgresql_replay_probe.py": ROOT / "scripts/ci/helper1_postgresql_replay_probe.py",
    "scripts/ci/helper1_product_approval_bundle.py": ROOT / "scripts/ci/helper1_product_approval_bundle.py",
    "scripts/ci/helper1_producer_package.py": ROOT / "scripts/ci/helper1_producer_package.py",
    "scripts/ci/publish_helper1_subject_check.py": ROOT / "scripts/ci/publish_helper1_subject_check.py",
    "scripts/verify_helper1_v51_package.py": ROOT / "scripts/verify_helper1_v51_package.py",
    "butler_pc_core/helper1/approval_closure.py": CANONICAL_ROOT / "approval_closure.py",
    "butler_pc_core/helper1/canonical_json.py": CANONICAL_ROOT / "canonical_json.py",
    "butler_pc_core/helper1/execution.py": CANONICAL_ROOT / "execution.py",
    "butler_pc_core/helper1/replay_store.py": CANONICAL_ROOT / "replay_store.py",
    "butler_pc_core/helper1/retrieval_policy.py": CANONICAL_ROOT / "retrieval_policy.py",
}

REQUIRED_FILES = (
    CANONICAL_ROOT / "__init__.py",
    CANONICAL_ROOT / "composition.py",
    CANONICAL_ROOT / "execution.py",
    CANONICAL_ROOT / "asset_lease.py",
    CANONICAL_ROOT / "contracts.py",
    CANONICAL_ROOT / "security.py",
    CANONICAL_ROOT / "ingestion.py",
    CANONICAL_ROOT / "index_store.py",
    CANONICAL_ROOT / "retrieval.py",
    CANONICAL_ROOT / "evaluation.py",
    CANONICAL_ROOT / "models.py",
    CANONICAL_ROOT / "measurement.py",
    CANONICAL_ROOT / "parser_isolation.py",
    CANONICAL_ROOT / "pipeline.py",
    CANONICAL_ROOT / "release.py",
    CANONICAL_ROOT / "service.py",
    CANONICAL_ROOT / "trace.py",
    CANONICAL_ROOT / "canonical_json.py",
    CANONICAL_ROOT / "replay_store.py",
    CANONICAL_ROOT / "retrieval_policy.py",
    CANONICAL_ROOT / "approval_closure.py",
    CANONICAL_ROOT / "test_evidence.py",
    ROUTE,
    CONTRACT_ROOT / "baseline-policy-v1.json",
    CONTRACT_ROOT / "ask-request-v2.schema.json",
    CONTRACT_ROOT / "answer-result-v2.schema.json",
    CONTRACT_ROOT / "canonical-subject-v1.schema.json",
    CONTRACT_ROOT / "egress-observation-v1.schema.json",
    CONTRACT_ROOT / "index-manifest-v2.schema.json",
    CONTRACT_ROOT / "parser-isolation-receipt-v1.schema.json",
    CONTRACT_ROOT / "release-receipt-v2.schema.json",
    CONTRACT_ROOT / "retrieval-evaluation-report-v1.schema.json",
    CONTRACT_ROOT / "retrieval-policy-v1.schema.json",
    CONTRACT_ROOT / "evidence-envelope-v1.schema.json",
    CONTRACT_ROOT / "retrieval-calibration-receipt-v1.schema.json",
    CONTRACT_ROOT / "retrieval-sealed-test-receipt-v1.schema.json",
    CONTRACT_ROOT / "retrieval-threshold-policy-v1.schema.json",
    CONTRACT_ROOT / "retrieval-approval-trust-policy-v1.json",
    ROOT / "scripts" / "ci" / "helper1_canonical_subject.py",
    TRUSTED_VERIFIER,
    *TRUSTED_COMPONENTS.values(),
    TRUSTED_POLICY,
)
FORBIDDEN = (
    "~/Desktop",
    "/private/tmp",
    "/Volumes/",
    "sys.path.append",
    "sys.path.insert",
    "import memory_helper",
    "pickle.load",
    "allow_pickle=True",
    "contract_only_response",
    "placeholder_answer",
)
REQUIRED_ROUTE_LITERALS = (
    "butler.helper1.ask-request.v2",
    "butler.helper1.index-request.v2",
    "/v1/helpers/1/index",
    "requested_generation_id",
    "effect_intent",
    "REQUEST_INVALID",
)
REQUIRED_MODEL_LITERALS = (
    "llama_model_load_from_file_ptr",
    "pass_fds=(model_fd,)",
    '"thinking": False',
    '"kv_disposed"',
)
REQUIRED_PIPELINE_LITERALS = (
    "bind_citations",
    "scan_runtime_text",
    "release_display",
    "detect_prompt_injection",
    "OS_EGRESS_VERIFIED",
    "RunTrace",
    "observed_search",
    "observed_index",
)
REQUIRED_EVALUATION_LITERALS = (
    "predicted_abstention and not record.answerable",
    "approved_calibration_receipt_sha256",
    "BLOCK_RETRIEVAL_POLICY_UNCALIBRATED",
)
PRODUCT_GATES = {
    "NATIVE_BOOKMARK_BRIDGE_OK": ROOT / "butler-desktop" / "src-tauri" / "src" / "helper1_bookmark.rs",
    "NATIVE_QWEN_WORKER_OK": ROOT / "butler-desktop" / "src-tauri" / "native" / "helper1_llama_worker.cpp",
    "APPROVED_ASSET_CLOSURE_OK": ROOT / "evidence" / "helper1" / "APPROVED_ASSET_CLOSURE.json",
    "REAL_ASSET_E2E_OK": ROOT / "evidence" / "helper1" / "REAL_ASSET_E2E_RECEIPT.json",
    "M3_M4_MEASUREMENT_OK": ROOT / "evidence" / "helper1" / "M3_M4_MEASUREMENT.json",
    "MACOS_SANDBOX_E2E_OK": ROOT / "evidence" / "helper1" / "MACOS_SANDBOX_E2E_RECEIPT.json",
}
CALLER_TRUST_OPTIONS = (
    "external_verifier",
    "external_verifier_sha256",
    "trust_key",
    "trust_key_sha256",
)
POLICY_KEYS = {
    "schema_version",
    "policy_epoch",
    "enabled",
    "repository",
    "producer_workflow_name",
    "producer_workflow_path",
    "handoff_chain_authority",
    "producer_package_contract",
    "protected_verifier_sha256",
    "protected_components_sha256",
    "approved_producer_identity",
    "approved_evidence_key_id",
    "approved_verdict_key_id",
    "approved_public_key_b64",
    "approved_public_key_sha256",
    "approved_verdict_public_key_b64",
    "approved_verdict_public_key_sha256",
    "approval_policy_sha256",
    "approved_activation_public_key_b64",
    "approved_activation_public_key_sha256",
    "required_approval_roles",
    "legacy_approval_role_bindings",
    "required_evidence_files",
    "subject_check_name",
    "subject_check_app_slug",
    "subject_check_required",
}


def valid_handoff_chain_authority(value: object) -> bool:
    if type(value) is not dict or set(value) != {
        "schema_version",
        "chain_id",
        "authority_mode",
        "approved_public_key_b64",
        "approved_public_key_sha256",
        "required_environment",
        "required_check_name",
    }:
        return False
    key = value.get("approved_public_key_b64")
    digest = value.get("approved_public_key_sha256")
    if (key is None) != (digest is None):
        return False
    if key is not None:
        try:
            decoded = base64.b64decode(key, validate=True)
        except (TypeError, ValueError):
            return False
        if len(decoded) != 32 or digest != "sha256:" + hashlib.sha256(decoded).hexdigest():
            return False
    return (
        value.get("schema_version") == "butler.helper1.handoff-chain-authority.v1"
        and value.get("chain_id") == "helper1-v51-a4-closure"
        and value.get("authority_mode") == "PROTECTED_WORKFLOW_SIGNED_CHAIN"
        and value.get("required_environment") == "helper1-production-verifier"
        and value.get("required_check_name") == "helper1-v2/protected-verdict"
    )


def valid_producer_package_contract(value: object) -> bool:
    def valid_record(record: object, generation: int) -> bool:
        return (
            type(record) is dict
            and set(record) == {"generation", "package_sha256", "result_tree"}
            and record.get("generation") == generation
            and type(record.get("package_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", record["package_sha256"]) is not None
            and type(record.get("result_tree")) is str
            and re.fullmatch(r"[0-9a-f]{40}", record["result_tree"]) is not None
        )

    return (
        type(value) is dict
        and set(value) == {
            "schema_version",
            "chain_id",
            "candidate_generation",
            "package_relative_path",
            "descriptor_relative_path",
            "immediate_predecessor",
            "rollback_record",
        }
        and value.get("schema_version") == "butler.helper1.producer-package-contract.v1"
        and value.get("chain_id") == "helper1-v51-a4-closure"
        and value.get("candidate_generation") == 15
        and value.get("package_relative_path") == "package/helper1-v51.zip"
        and value.get("descriptor_relative_path") == "package/helper1-v51.candidate.json"
        and valid_record(value.get("immediate_predecessor"), 14)
        and valid_record(value.get("rollback_record"), 13)
        and value["immediate_predecessor"] != value["rollback_record"]
    )


def emit(key: str, value: int | str) -> None:
    print(f"{key}={value}")


def source_files() -> tuple[Path, ...]:
    return tuple(sorted(CANONICAL_ROOT.glob("*.py"))) + (ROUTE,)


def static_audit() -> tuple[bool, str]:
    if any(not path.is_file() for path in REQUIRED_FILES):
        return False, "HELPER1_REQUIRED_FILE_MISSING"
    try:
        sources = {path: path.read_text(encoding="utf-8") for path in source_files()}
    except (OSError, UnicodeError):
        return False, "HELPER1_SOURCE_READ_FAILED"
    if any(token in text for text in sources.values() for token in FORBIDDEN):
        return False, "HELPER1_FORBIDDEN_SOURCE_TOKEN"
    if any(token not in sources[ROUTE] for token in REQUIRED_ROUTE_LITERALS):
        return False, "HELPER1_REQUEST_CONTRACT_MISSING"
    if any(token not in sources[CANONICAL_ROOT / "models.py"] for token in REQUIRED_MODEL_LITERALS):
        return False, "HELPER1_MODEL_CONTRACT_MISSING"
    if any(token not in sources[CANONICAL_ROOT / "pipeline.py"] for token in REQUIRED_PIPELINE_LITERALS):
        return False, "HELPER1_PIPELINE_GATE_MISSING"
    if any(
        token not in sources[CANONICAL_ROOT / "evaluation.py"]
        for token in REQUIRED_EVALUATION_LITERALS
    ):
        return False, "HELPER1_EVALUATION_GATE_MISSING"
    approval_closure = sources[CANONICAL_ROOT / "approval_closure.py"]
    service = sources[CANONICAL_ROOT / "service.py"]
    if any(
        token not in approval_closure
        for token in (
            "A4_RETRIEVAL_CALIBRATION_RECEIPT",
            "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
            "A4_RETRIEVAL_THRESHOLD_POLICY",
            "reserve(reservations, now)",
            "A4_METRIC_RECOMPUTE_MISMATCH",
        )
    ) or any(
        token not in service
        for token in (
            "retrieval_policy_authority.is_production_authority",
            "closure_verdict.release_allowed",
            "HELPER1_APPROVAL_CLOSURE_REQUIRED",
        )
    ):
        return False, "HELPER1_A4_APPROVAL_CLOSURE_MISSING"
    try:
        policy = json.loads(TRUSTED_POLICY.read_text(encoding="utf-8"))
        if type(policy) is not dict or set(policy) != POLICY_KEYS:
            return False, "HELPER1_TRUST_POLICY_SCHEMA_INVALID"
        if (
            policy["schema_version"] != "butler.helper1.trusted-verifier-policy.v1"
            or type(policy["policy_epoch"]) is not int
            or policy["policy_epoch"] < 1
            or type(policy["enabled"]) is not bool
            or policy["repository"] != "tristan00037-tristan050/tristan050-ai_ondevice_APP"
            or policy["producer_workflow_name"] != "helper1-v2-evidence-producer"
            or policy["producer_workflow_path"] != ".github/workflows/helper1-v2-evidence.yml"
            or not valid_handoff_chain_authority(policy["handoff_chain_authority"])
            or not valid_producer_package_contract(policy["producer_package_contract"])
            or policy["approved_producer_identity"] != "sha256:44804ccc81a9a1008ab0fe6110a086c2ea918fd107a1bed199f46f0f09d7c126"
            or policy["approved_evidence_key_id"] != "butler/helper1/evidence/ed25519/v1"
            or policy["approved_verdict_key_id"] != "butler/helper1/verdict/ed25519/v1"
            or type(policy["protected_verifier_sha256"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", policy["protected_verifier_sha256"]) is None
            or policy["protected_verifier_sha256"] != "sha256:" + hashlib.sha256(TRUSTED_VERIFIER.read_bytes()).hexdigest()
            or type(policy["protected_components_sha256"]) is not dict
            or policy["protected_components_sha256"] != {
                name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in TRUSTED_COMPONENTS.items()
            }
            or policy["subject_check_name"] != "helper1-v2/protected-verdict"
            or policy["subject_check_app_slug"] != "github-actions"
            or policy["subject_check_required"] is not True
            or type(policy["required_evidence_files"]) is not list
            or len(policy["required_evidence_files"]) != 4
            or len(set(policy["required_evidence_files"])) != 4
            or policy["required_approval_roles"] != [
                "A1_STARTUP_COMPOSITION_RECEIPT",
                "A2_SUBJECT_BINDING_RECEIPT",
                "A3_EGRESS_OBSERVATION_RECEIPT",
                "A4_RETRIEVAL_CALIBRATION_RECEIPT",
                "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
                "A5_PARSER_ISOLATION_RECEIPT",
                "A4_RETRIEVAL_THRESHOLD_POLICY",
            ]
            or policy["legacy_approval_role_bindings"] != {
                "A1_STARTUP_COMPOSITION_RECEIPT": "APPROVED_ASSET_CLOSURE.json",
                "A2_SUBJECT_BINDING_RECEIPT": "REAL_ASSET_E2E_RECEIPT.json",
                "A3_EGRESS_OBSERVATION_RECEIPT": "M3_M4_MEASUREMENT.json",
                "A5_PARSER_ISOLATION_RECEIPT": "MACOS_SANDBOX_E2E_RECEIPT.json",
            }
        ):
            return False, "HELPER1_TRUST_POLICY_SCHEMA_INVALID"
        trust_values = (
            policy["approved_public_key_b64"],
            policy["approved_public_key_sha256"],
            policy["approved_verdict_public_key_b64"],
            policy["approved_verdict_public_key_sha256"],
            policy["approval_policy_sha256"],
            policy["approved_activation_public_key_b64"],
            policy["approved_activation_public_key_sha256"],
        )
        if policy["enabled"]:
            if any(type(value) is not str or not value for value in trust_values):
                return False, "HELPER1_TRUST_POLICY_INCOMPLETE"
        elif any(value is not None for value in trust_values):
            return False, "HELPER1_DISABLED_POLICY_HAS_TRUST_MATERIAL"
        from jsonschema import Draft202012Validator

        for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
            Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
        approval_policy = json.loads(
            (CONTRACT_ROOT / "retrieval-approval-trust-policy-v1.json").read_text(
                encoding="utf-8"
            )
        )
        if approval_policy != {
            "enabled": False,
            "keys": [],
            "max_evidence_age_seconds": 86400,
            "policy_epoch": 1,
            "repository": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
            "schema_version": "butler.helper1.retrieval-approval-trust-policy.v1",
        }:
            return False, "HELPER1_A4_POLICY_NOT_DISABLED"
    except (ImportError, KeyError, OSError, UnicodeError, ValueError):
        return False, "HELPER1_SCHEMA_VERIFY_FAILED"
    if re.search(r"\b(?:print|logging\.\w+)\s*\(", "\n".join(sources.values())):
        return False, "HELPER1_RAW_LOG_SURFACE_PRESENT"
    return True, "NONE"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--static-only", action="store_true")
    # Deprecated attack-surface arguments are parsed only to return a stable
    # fail-closed verdict instead of argparse diagnostics.
    parser.add_argument("--evidence-dir")
    parser.add_argument("--external-verifier")
    parser.add_argument("--external-verifier-sha256")
    parser.add_argument("--trust-key")
    parser.add_argument("--trust-key-sha256")
    parser.add_argument("--subject-commit")
    parser.add_argument("--subject-tree")
    return parser


def main() -> int:
    args = _parser().parse_args()
    static_ok, error = static_audit()
    emit("HELPER1_STATIC_VERIFY_OK", int(static_ok))
    if args.static_only:
        emit("ERROR_CODE", error)
        return 0 if static_ok else 1
    caller_selected = any(getattr(args, name) is not None for name in CALLER_TRUST_OPTIONS)
    for key, path in PRODUCT_GATES.items():
        emit(key, int(path.is_file()))
    emit("PRODUCT_RELEASE_ALLOWED", 0)
    emit("RUNTIME_ACTIVATION_ALLOWED", 0)
    emit("HELPER1_PRODUCTION_CLAIM_ALLOWED", 0)
    emit("CODE_PASS", 0)
    if not static_ok:
        verdict = error
    elif caller_selected:
        verdict = "CALLER_SELECTED_TRUST_FORBIDDEN"
    else:
        verdict = "PROTECTED_TRUSTED_VERIFIER_REQUIRED"
    emit("ERROR_CODE", verdict)
    return 1


if __name__ == "__main__":
    sys.exit(main())
