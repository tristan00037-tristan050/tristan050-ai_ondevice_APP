from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path

from .attestation import load_trust_policy
from .canonical import canonical_sha256, read_json_closed, write_canonical_json
from .errors import ExitCode, FailClass, GateError
from .model_manifest import verify_model_manifest
from .policy import load_approved_policy
from .preflight import validate_m3_gate_receipts
from .product_bridge import ADAPTER_ENTRYPOINT, validate_product_module
from .schedule import build_schedule, verify_fixture_manifest


def run(args: argparse.Namespace) -> dict[str, object]:
    # Direct invocation cannot bypass any preflight; all gates are rechecked here.
    policy_receipt = load_approved_policy(args.policy, expected_sha256=args.policy_sha256)
    load_trust_policy(args.trust_policy, expected_sha256=args.trust_policy_sha256)
    expected_subjects = read_json_closed(args.preflight_subjects)
    if canonical_sha256(expected_subjects) != args.preflight_subjects_sha256:
        _block("PREFLIGHT_SUBJECTS_DIGEST", ExitCode.DIGEST)
    gate_receipts = [read_json_closed(path) for path in sorted(args.preflight_receipts.glob("*.json"))]
    validate_m3_gate_receipts(gate_receipts, expected_subjects=expected_subjects)
    identity = validate_product_module(
        args.product_module,
        approved_product_root=args.product_root,
        expected_module_sha256=args.product_module_sha256,
        expected_commit_oid=args.product_commit_oid,
    )
    fixtures = read_json_closed(args.fixture_manifest); verify_fixture_manifest(fixtures)
    candidate_a = read_json_closed(args.candidate_a); candidate_b = read_json_closed(args.candidate_b)
    verify_model_manifest(args.model_a_root, candidate_a); verify_model_manifest(args.model_b_root, candidate_b)
    policy = dict(policy_receipt.normalized); policy["_payload_sha256"] = policy_receipt.canonical_sha256
    if candidate_a["model_manifest_sha256"] != policy["candidates"]["A"]["model_manifest_sha256"] or candidate_b["model_manifest_sha256"] != policy["candidates"]["B"]["model_manifest_sha256"]:
        _block("MODEL_POLICY_BINDING", ExitCode.DIGEST)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    schedule = build_schedule(policy, fixtures); schedule_path = output / "schedule.jcs.json"; write_canonical_json(schedule_path, schedule)
    module = importlib.import_module(args.product_module); adapter = getattr(module, ADAPTER_ENTRYPOINT)
    result = adapter(
        policy_path=args.policy.resolve(), fixture_manifest_path=args.fixture_manifest.resolve(),
        candidate_a_manifest_path=args.candidate_a.resolve(), candidate_b_manifest_path=args.candidate_b.resolve(),
        schedule_path=schedule_path, output_root=output, product_identity_sha256=identity["product_identity_sha256"],
        runtime_activation_allowed=0,
    )
    if not isinstance(result, dict) or set(result) != {"run_id", "evidence_root_relative"}:
        _block("PRODUCT_ADAPTER_RESULT", ExitCode.SCHEMA)
    relative = Path(result["evidence_root_relative"])
    if relative.is_absolute() or ".." in relative.parts:
        _block("EVIDENCE_PATH", ExitCode.SECURITY)
    evidence_root = (output / relative).resolve(strict=True)
    if output not in evidence_root.parents:
        _block("EVIDENCE_PATH_ESCAPE", ExitCode.SECURITY)
    verifier = Path(__file__).resolve().parents[1] / "offline_verifier" / "verify.py"
    completed = subprocess.run([sys.executable, str(verifier), str(evidence_root), "--mode", "m3-evidence"], stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise GateError(FailClass.INDEPENDENT_VERIFY, "OFFLINE_VERIFIER_BLOCK", exit_code=completed.returncode)
    # F-003: consume the verifier's separated structural/semantic verdicts. Emit
    # M3_EVIDENCE_VALID=1 only when BOTH structural and semantic re-verification pass;
    # otherwise stay fail-closed (structure alone can never claim M3 evidence).
    try:
        verdict = json.loads(completed.stdout)
    except (ValueError, json.JSONDecodeError):
        raise GateError(FailClass.INDEPENDENT_VERIFY, "OFFLINE_VERIFIER_OUTPUT", exit_code=ExitCode.SCHEMA)
    structural = verdict.get("structural") if isinstance(verdict, dict) else None
    semantic = verdict.get("semantic") if isinstance(verdict, dict) else None
    structural_pass = isinstance(structural, dict) and structural.get("status") == "M3_ARTIFACT_STRUCTURE_PASS"
    semantic_pass = isinstance(semantic, dict) and semantic.get("status") == "M3_SEMANTIC_PASS"
    m3_evidence_valid = 1 if structural_pass and semantic_pass and verdict.get("m3_evidence_valid") == 1 else 0
    return {
        "status": "M3_EVIDENCE_VALID" if m3_evidence_valid == 1 else "M3_ARTIFACT_STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED",
        "run_id": result["run_id"],
        "structural_pass": structural_pass,
        "semantic_pass": semantic_pass,
        "m3_evidence_valid": m3_evidence_valid,
        "g1_ready": bool(m3_evidence_valid),
        "runtime_activation_allowed": 0,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(allow_abbrev=False)
    value.add_argument("--policy", type=Path, required=True); value.add_argument("--policy-sha256", required=True)
    value.add_argument("--trust-policy", type=Path, required=True); value.add_argument("--trust-policy-sha256", required=True)
    value.add_argument("--preflight-receipts", type=Path, required=True); value.add_argument("--preflight-subjects", type=Path, required=True); value.add_argument("--preflight-subjects-sha256", required=True)
    value.add_argument("--fixture-manifest", type=Path, required=True); value.add_argument("--candidate-a", type=Path, required=True); value.add_argument("--candidate-b", type=Path, required=True)
    value.add_argument("--model-a-root", type=Path, required=True); value.add_argument("--model-b-root", type=Path, required=True)
    value.add_argument("--product-module", required=True); value.add_argument("--product-root", type=Path, required=True); value.add_argument("--product-module-sha256", required=True); value.add_argument("--product-commit-oid", required=True)
    value.add_argument("--output", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        print(json.dumps(run(parser().parse_args(argv)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))); return 0
    except GateError as exc:
        print(json.dumps(exc.as_safe_dict(), sort_keys=True, separators=(",", ":"))); return int(exc.exit_code)
    except Exception:
        error = GateError(FailClass.INTERNAL_VERIFIER_ERROR, "OWNER_RUNNER_UNHANDLED", exit_code=ExitCode.INTERNAL)
        print(json.dumps(error.as_safe_dict(), sort_keys=True, separators=(",", ":"))); return int(error.exit_code)


def _block(detail: str, code: ExitCode) -> None:
    raise GateError(FailClass.PREFLIGHT, detail, exit_code=code)


if __name__ == "__main__":
    sys.exit(main())
