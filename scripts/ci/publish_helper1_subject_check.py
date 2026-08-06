#!/usr/bin/env python3
"""Publish the protected Helper1 verdict on the exact evidence subject SHA."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from helper1_subject_binding import SubjectBindingError, resolve_commit_tree
from helper1_protected_surface import PROTECTED_COMPONENT_PATHS

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
CHECK_NAME = "helper1-v2/protected-verdict"
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
GIT_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_JSON_BYTES = 256 * 1024
REQUIRED_APPROVAL_ROLES = [
    "A1_STARTUP_COMPOSITION_RECEIPT",
    "A2_SUBJECT_BINDING_RECEIPT",
    "A3_EGRESS_OBSERVATION_RECEIPT",
    "A4_RETRIEVAL_CALIBRATION_RECEIPT",
    "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
    "A5_PARSER_ISOLATION_RECEIPT",
    "A4_RETRIEVAL_THRESHOLD_POLICY",
]
LEGACY_APPROVAL_BINDINGS = {
    "A1_STARTUP_COMPOSITION_RECEIPT": "APPROVED_ASSET_CLOSURE.json",
    "A2_SUBJECT_BINDING_RECEIPT": "REAL_ASSET_E2E_RECEIPT.json",
    "A3_EGRESS_OBSERVATION_RECEIPT": "M3_M4_MEASUREMENT.json",
    "A5_PARSER_ISOLATION_RECEIPT": "MACOS_SANDBOX_E2E_RECEIPT.json",
}
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
    "quality_evidence_required",
    "quality_producer_workflow_id",
    "quality_producer_workflow_path",
    "quality_producer_workflow_sha256",
    "device_trust_policy_sha256",
}
PROTECTED_COMPONENTS = {path: ROOT / path for path in PROTECTED_COMPONENT_PATHS}
VERDICT_KEYS = {
    "schema_version",
    "code_pass",
    "product_release_allowed",
    "runtime_activation_allowed",
    "production_claim_allowed",
    "subject_commit",
    "subject_tree",
    "producer_run",
    "policy_epoch",
    "verdict_key_id",
    "policy_sha256",
    "verifier_sha256",
    "producer_package_sha256",
    "chain_authority_sha256",
    "evidence_bundle_sha256",
    "search_quality_evidence_sha256",
    "issued_at_epoch_s",
    "error_code",
    "signature_b64",
}


class CheckPublishError(RuntimeError):
    pass


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
        if len(decoded) != 32 or digest != sha256(decoded):
            return False
    return (
        value.get("schema_version") == "butler.helper1.handoff-chain-authority.v1"
        and value.get("chain_id") == "helper1-v51-a4-closure"
        and value.get("authority_mode") == "PROTECTED_WORKFLOW_SIGNED_CHAIN"
        and value.get("required_environment") == "helper1-production-verifier"
        and value.get("required_check_name") == CHECK_NAME
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


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_object(path: Path, code: str) -> tuple[dict[str, Any], bytes]:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or not 0 < info.st_size <= MAX_JSON_BYTES:
            raise CheckPublishError(code)
        raw = path.read_bytes()
        value = json.loads(
            raw,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise CheckPublishError(code) from exc
    if type(value) is not dict:
        raise CheckPublishError(code)
    return value, raw


def validate_policy(policy: dict[str, Any]) -> None:
    if (
        set(policy) != POLICY_KEYS
        or policy.get("schema_version") != "butler.helper1.trusted-verifier-policy.v1"
        or policy.get("repository") != REPOSITORY
        or type(policy.get("enabled")) is not bool
        or type(policy.get("policy_epoch")) is not int
        or policy["policy_epoch"] < 1
        or type(policy.get("protected_components_sha256")) is not dict
        or set(policy["protected_components_sha256"]) != set(PROTECTED_COMPONENTS)
        or type(policy.get("quality_producer_workflow_path")) is not str
        or type(policy.get("quality_producer_workflow_sha256")) is not str
        or SHA256.fullmatch(policy["quality_producer_workflow_sha256"]) is None
        or policy["protected_components_sha256"].get(
            policy["quality_producer_workflow_path"]
        )
        != policy["quality_producer_workflow_sha256"]
        or policy.get("subject_check_name") != CHECK_NAME
        or policy.get("subject_check_app_slug") != "github-actions"
        or policy.get("subject_check_required") is not True
        or policy.get("required_approval_roles") != REQUIRED_APPROVAL_ROLES
        or policy.get("legacy_approval_role_bindings") != LEGACY_APPROVAL_BINDINGS
        or not valid_handoff_chain_authority(policy.get("handoff_chain_authority"))
        or not valid_producer_package_contract(policy.get("producer_package_contract"))
    ):
        raise CheckPublishError("TRUST_POLICY_INVALID")
    try:
        observed = {name: sha256(path.read_bytes()) for name, path in PROTECTED_COMPONENTS.items()}
    except OSError as exc:
        raise CheckPublishError("PROTECTED_COMPONENT_UNAVAILABLE") from exc
    if observed != policy["protected_components_sha256"]:
        raise CheckPublishError("PROTECTED_COMPONENT_DIGEST_MISMATCH")
    if policy.get("protected_verifier_sha256") != observed["scripts/ci/helper1_trusted_verifier.py"]:
        raise CheckPublishError("PROTECTED_VERIFIER_DIGEST_MISMATCH")


def subject_from_event(path: Path) -> tuple[str, str]:
    event, _ = load_object(path, "WORKFLOW_EVENT_INVALID")
    repository = event.get("repository")
    run = event.get("workflow_run")
    if type(repository) is not dict or type(run) is not dict:
        raise CheckPublishError("WORKFLOW_EVENT_INVALID")
    subject = run.get("head_sha")
    if (
        repository.get("full_name") != REPOSITORY
        or type(subject) is not str
        or GIT_OBJECT.fullmatch(subject) is None
        or type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
    ):
        raise CheckPublishError("WORKFLOW_EVENT_SUBJECT_INVALID")
    return subject, f"{run['id']}:{run['run_attempt']}"


def verify_success_verdict(
    verdict: dict[str, Any],
    policy: dict[str, Any],
    subject: str,
    producer_run: str,
    subject_tree: str,
) -> bool:
    if set(verdict) != VERDICT_KEYS:
        return False
    if (
        verdict.get("schema_version") != "butler.helper1.trusted-verdict.v1"
        or verdict.get("code_pass") is not True
        or verdict.get("product_release_allowed") is not True
        or verdict.get("runtime_activation_allowed") is not True
        or verdict.get("production_claim_allowed") is not True
        or verdict.get("subject_commit") != subject
        or verdict.get("producer_run") != producer_run
        or verdict.get("subject_tree") != subject_tree
        or verdict.get("policy_epoch") != policy.get("policy_epoch")
        or verdict.get("verdict_key_id") != policy.get("approved_verdict_key_id")
        or verdict.get("policy_sha256") != sha256(POLICY_PATH.read_bytes())
        or verdict.get("verifier_sha256") != policy.get("protected_verifier_sha256")
        or type(verdict.get("producer_package_sha256")) is not str
        or SHA256.fullmatch(verdict["producer_package_sha256"]) is None
        or type(verdict.get("chain_authority_sha256")) is not str
        or SHA256.fullmatch(verdict["chain_authority_sha256"]) is None
        or type(verdict.get("evidence_bundle_sha256")) is not str
        or SHA256.fullmatch(verdict["evidence_bundle_sha256"]) is None
        or type(verdict.get("search_quality_evidence_sha256")) is not str
        or SHA256.fullmatch(verdict["search_quality_evidence_sha256"]) is None
        or type(verdict.get("issued_at_epoch_s")) is not int
        or verdict.get("error_code") != "NONE"
        or type(verdict.get("signature_b64")) is not str
        or policy.get("enabled") is not True
    ):
        return False
    try:
        public = base64.b64decode(
            policy["approved_verdict_public_key_b64"], validate=True
        )
        signature = base64.b64decode(verdict["signature_b64"], validate=True)
        if (
            len(public) != 32
            or len(signature) != 64
            or sha256(public) != policy["approved_verdict_public_key_sha256"]
        ):
            return False
        unsigned = {key: item for key, item in verdict.items() if key != "signature_b64"}
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, canonical_json(unsigned)
        )
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False
    return True


def build_check_payload(
    *,
    subject: str,
    producer_run: str,
    verdict: dict[str, Any],
    verdict_digest: str,
    policy: dict[str, Any],
    details_url: str,
    subject_tree: str,
    prerequisites_ok: bool,
) -> tuple[dict[str, Any], str, str]:
    success = prerequisites_ok and verify_success_verdict(
        verdict, policy, subject, producer_run, subject_tree
    )
    conclusion = "success" if success else "failure"
    error_code = verdict.get("error_code")
    if not prerequisites_ok and error_code == "NONE":
        error_code = "PROTECTED_PREREQUISITE_FAILED"
    elif not success and error_code == "NONE":
        error_code = "PROTECTED_VERDICT_INVALID"
    if type(error_code) is not str or not error_code or len(error_code) > 128:
        error_code = "PROTECTED_VERDICT_INVALID"
    summary = "\n".join(
        [
            f"subject_commit={subject}",
            f"subject_tree={subject_tree}",
            f"verdict_digest={verdict_digest}",
            f"policy_epoch={policy.get('policy_epoch', 0)}",
            f"verifier_digest={verdict.get('verifier_sha256', 'unavailable')}",
            f"producer_run={producer_run}",
            f"error_code={'NONE' if success else error_code}",
        ]
    )
    payload = {
        "name": CHECK_NAME,
        "head_sha": subject,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": details_url,
        "external_id": f"helper1-v2:{subject}:{producer_run}",
        "output": {
            "title": "Helper1 v2 protected subject verdict",
            "summary": summary,
        },
    }
    return payload, conclusion, "NONE" if success else error_code


def publish(payload: dict[str, Any], token: str) -> tuple[int, str]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/check-runs",
        data=canonical_json(payload),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "butler-helper1-protected-verifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read(MAX_JSON_BYTES))
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise CheckPublishError("SUBJECT_CHECK_PUBLISH_FAILED") from exc
    if (
        type(value) is not dict
        or type(value.get("id")) is not int
        or value.get("name") != CHECK_NAME
        or value.get("head_sha") != payload["head_sha"]
        or value.get("status") != "completed"
        or value.get("conclusion") != payload["conclusion"]
    ):
        raise CheckPublishError("SUBJECT_CHECK_RESPONSE_INVALID")
    url = value.get("html_url")
    if type(url) is not str or not url.startswith("https://github.com/"):
        raise CheckPublishError("SUBJECT_CHECK_RESPONSE_INVALID")
    return value["id"], url


def write_record(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json(value) + b"\n")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--verdict", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--publish", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    subject: str | None = None
    producer_run: str | None = None
    try:
        subject, producer_run = subject_from_event(args.event)
        try:
            subject_tree = resolve_commit_tree(ROOT, subject)
        except SubjectBindingError as exc:
            raise CheckPublishError(str(exc)) from exc
        policy, _ = load_object(POLICY_PATH, "TRUST_POLICY_INVALID")
        validate_policy(policy)
        verdict, verdict_bytes = load_object(args.verdict, "PROTECTED_VERDICT_INVALID")
        verdict_digest = sha256(verdict_bytes)
        details_url = (
            f"https://github.com/{REPOSITORY}/actions/runs/"
            f"{os.environ.get('GITHUB_RUN_ID', '0')}"
        )
        prerequisites_ok = all(
            os.environ.get(name) == "success"
            for name in (
                "HELPER1_REGRESSION_OUTCOME",
                "HELPER1_REPLAY_PROBE_OUTCOME",
                "HELPER1_LINEAGE_OUTCOME",
                "HELPER1_FETCH_OUTCOME",
                "HELPER1_DOWNLOAD_OUTCOME",
                "HELPER1_VERIFY_OUTCOME",
                "HELPER1_PRESERVE_OUTCOME",
            )
        )
        payload, conclusion, error_code = build_check_payload(
            subject=subject,
            producer_run=producer_run,
            verdict=verdict,
            verdict_digest=verdict_digest,
            policy=policy,
            details_url=details_url,
            subject_tree=subject_tree,
            prerequisites_ok=prerequisites_ok,
        )
        check_id: int | None = None
        check_url: str | None = None
        if args.publish:
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                raise CheckPublishError("SUBJECT_CHECK_TOKEN_MISSING")
            check_id, check_url = publish(payload, token)
        write_record(
            args.record,
            {
                "schema_version": "butler.helper1.subject-check-publication.v1",
                "check_name": CHECK_NAME,
                "subject_commit": subject,
                "producer_run": producer_run,
                "verdict_digest": verdict_digest,
                "conclusion": conclusion,
                "error_code": error_code,
                "published": bool(args.publish),
                "check_run_id": check_id,
                "check_run_url": check_url,
            },
        )
        print(f"SUBJECT_CHECK_PUBLISHED={int(bool(args.publish))}")
        print(f"SUBJECT_CHECK_CONCLUSION={conclusion.upper()}")
        if conclusion != "success":
            print(f"ERROR_CODE={error_code}")
            return 1
        print("ERROR_CODE=NONE")
        return 0
    except (CheckPublishError, OSError, KeyError, TypeError, ValueError) as exc:
        code = str(exc) if isinstance(exc, CheckPublishError) else "SUBJECT_CHECK_FAILED"
        try:
            write_record(
                args.record,
                {
                    "schema_version": "butler.helper1.subject-check-publication.v1",
                    "check_name": CHECK_NAME,
                    "subject_commit": subject,
                    "producer_run": producer_run,
                    "verdict_digest": None,
                    "conclusion": "failure",
                    "error_code": code,
                    "published": False,
                    "check_run_id": None,
                    "check_run_url": None,
                },
            )
        except OSError:
            code = "SUBJECT_CHECK_RECORD_WRITE_FAILED"
        print("SUBJECT_CHECK_PUBLISHED=0")
        print("SUBJECT_CHECK_CONCLUSION=FAILURE")
        print(f"ERROR_CODE={code}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
