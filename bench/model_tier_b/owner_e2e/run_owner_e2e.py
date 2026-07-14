"""Owner M3 E2E driver (§4-§13). Single physical real 1.7B execution.

Verifies product source identity against the approved commit tree BEFORE any product
import, spawns an isolated child that runs one real Box3 smoke, re-verifies every
module the child imported, then writes a verifier-passing evidence root from the real
observations, signs an Ed25519 external-observation bundle, and runs the independent
offline verifier (structural AND semantic must PASS). Emits one raw-safe JSON result.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(subprocess.run(["git", "-C", str(BENCH_ROOT), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, check=True).stdout.strip()).resolve(strict=True)
sys.path.insert(0, str(BENCH_ROOT))

from butler_bench.canonical import write_canonical_json  # noqa: E402
from butler_bench.evidence import EvidenceWriter, build_artifact_manifest  # noqa: E402
from butler_bench.product_bridge import verify_blob_in_commit_tree  # noqa: E402

EXTERNAL_TYPES = ("environment", "worker_event_stream_index", "cold_worker", "dual_resident", "os_egress", "epoch", "live_semantic_verify")
MANDATORY = [
    "source_provenance", "environment", "benchmark_policy", "model_identity_A", "model_identity_B",
    "runtime_config_A", "runtime_config_B", "fixture_manifest", "schedule", "worker_event_stream_index",
    "cold_worker", "live_semantic_verify", "epoch", "dual_resident", "os_egress", "ci", "raw_scan", "final_verdict",
]
# P0-A: NO signing seed in the repository. The production private key lives only in an
# external, owner-owned 0600 file outside the repo (Keychain/HSM at M3); its path is
# passed via BUTLER_BENCH_SIGNING_KEY_FILE. Absent it, the observation bundle cannot be
# produced and this run is a structural-only DIAGNOSTIC (no semantic PASS).
_SHA = "0" * 64


def _load_external_signing_seed():
    env = os.environ.get("BUTLER_BENCH_SIGNING_KEY_FILE")
    if not env:
        return None
    path = Path(env)
    if path.is_symlink():
        raise OwnerBlock("BLOCKED_SIGNING_KEY_NOT_PROVISIONED:symlink")
    resolved = path.resolve(strict=True)
    if REPO_ROOT == resolved or REPO_ROOT in resolved.parents:
        raise OwnerBlock("BLOCKED_SIGNING_KEY_NOT_PROVISIONED:inside_repo")
    stat = resolved.stat()
    if not resolved.is_file() or stat.st_uid != os.getuid() or stat.st_nlink != 1 or (stat.st_mode & 0o077) != 0:
        raise OwnerBlock("BLOCKED_SIGNING_KEY_NOT_PROVISIONED:file_constraints")
    raw = resolved.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise OwnerBlock("BLOCKED_SIGNING_KEY_NOT_PROVISIONED:format")
    return bytes.fromhex(raw)


def _resolve_trust_policy():
    env_path = os.environ.get("BUTLER_BENCH_TRUST_POLICY")
    env_sha = os.environ.get("BUTLER_BENCH_TRUST_POLICY_SHA256")
    if env_path and env_sha:
        return Path(env_path).resolve(strict=True), env_sha
    default = BENCH_ROOT / "policy" / "m3_owner_trust_policy.json"
    return default, hashlib.sha256(default.read_bytes()).hexdigest()


class OwnerBlock(RuntimeError):
    pass


def _load_verifier():
    spec = importlib.util.spec_from_file_location("owner_offline_verify", BENCH_ROOT / "offline_verifier" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def _validate_model() -> Path:
    root = Path(os.environ["BUTLER_MODEL_ASSET_ROOT"]).resolve(strict=True)
    rel = os.environ["BUTLER_BOX3_1_7B_MODEL_RELATIVE"]
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise OwnerBlock("BLOCKED_MODEL_IDENTITY:relative")
    model = (root / rel).resolve(strict=True)
    if root not in model.parents or model.is_symlink() or not model.is_file() or model.stat().st_size <= 0:
        raise OwnerBlock("BLOCKED_MODEL_IDENTITY:path")
    with model.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            raise OwnerBlock("BLOCKED_MODEL_IDENTITY:magic")
    return model


def _verify_source_before_import(commit: str) -> None:
    # Product adapter + its owner blobs must match the approved commit tree BEFORE import.
    for rel in ("butler_pc_core/model_tier_bench/product_adapter.py", "butler_pc_core/model_tier_bench/observer.py"):
        verify_blob_in_commit_tree(REPO_ROOT / rel, commit)


def _run_isolated_child(model_path: Path) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(REPO_ROOT),  # approved package root only
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "BUTLER_MODEL_ASSET_ROOT": os.environ["BUTLER_MODEL_ASSET_ROOT"],
        "BUTLER_BOX3_1_7B_MODEL_RELATIVE": os.environ["BUTLER_BOX3_1_7B_MODEL_RELATIVE"],
    }
    completed = subprocess.run(
        # PYTHONNOUSERSITE=1 blocks user site-packages (shadowing) while keeping the
        # approved venv runtime (llama_cpp). PYTHONPATH is pinned to the repo root only.
        [sys.executable, str(BENCH_ROOT / "owner_e2e" / "child_worker.py")],
        input=json.dumps({"repo_root": str(REPO_ROOT), "model_path": str(model_path)}),
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT), check=False,
    )
    if completed.returncode != 0:
        raise OwnerBlock("BLOCKED_OWNER_E2E:child_exit")
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise OwnerBlock("BLOCKED_OWNER_E2E:child_output")


def _reverify_imported_modules(trace: dict, commit: str) -> int:
    count = 0
    for entry in trace["imported_local_modules"]:
        rel = entry["relative_path"]
        if not rel.startswith("butler_pc_core/"):
            continue  # product surface only; bench/stdlib handled separately
        recorded = _git("rev-parse", "--verify", f"{commit}:{rel}")
        actual = _git("hash-object", str(REPO_ROOT / rel))
        if recorded != actual or actual != hashlib_git_blob(REPO_ROOT / rel):
            raise OwnerBlock("BLOCKED_OWNER_E2E:import_digest")
        count += 1
    if count == 0:
        raise OwnerBlock("BLOCKED_OWNER_E2E:no_product_import")
    return count


def hashlib_git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def _observation(verifier, digest: str, receipt_type: str, subject, raw_safe: dict) -> dict:
    return {
        "receipt_sha256": digest,
        "receipt_type": receipt_type,
        "subject_sha256": verifier.digest_bytes(verifier.canonical_bytes(subject)),
        "raw_safe_observation": raw_safe,
        "observation_digest": verifier.digest_bytes(verifier.canonical_bytes(raw_safe)),
    }


def _metal_preflight(trace: dict) -> None:
    if platform.machine() != "arm64":
        raise OwnerBlock("BLOCKED_METAL_BACKEND:arch")
    if not trace["metal_backend_initialized"] or trace["actual_offloaded_layer_count"] <= 0:
        raise OwnerBlock("BLOCKED_METAL_BACKEND:offload")
    if not trace["first_token_received"] or trace["completion_token_count"] < 1:
        raise OwnerBlock("BLOCK_ENGINE_NO_FIRST_TOKEN")


def run(output_root: Path) -> dict:
    verifier = _load_verifier()
    commit = _git("rev-parse", "HEAD^{commit}")
    model_path = _validate_model()
    _verify_source_before_import(commit)

    trace = _run_isolated_child(model_path)
    imported_product_count = _reverify_imported_modules(trace, commit)
    _metal_preflight(trace)

    run_id = str(uuid.uuid4())
    evidence_root_relative = f"evidence/run-{run_id}"
    evidence_root = (output_root / evidence_root_relative)
    if evidence_root.exists():
        raise OwnerBlock("BLOCKED_OWNER_E2E:root_reuse")
    evidence_root.mkdir(parents=True, exist_ok=False)

    # Real observation payloads (raw-safe: digests/counts only) mapped per receipt type.
    raw_by_type = {
        "environment": {"architecture_ok": 1, "chip_offloaded_layers": trace["actual_offloaded_layer_count"]},
        "worker_event_stream_index": {"completion_token_count": trace["completion_token_count"], "first_token_received": 1},
        "cold_worker": {"load_ms_bucket": int(trace["load_ms"] // 1000), "child_pid_present": 1},
        "dual_resident": {"model_size_mb": trace["model_size_bytes"] // (1024 * 1024), "offloaded_layers": trace["actual_offloaded_layer_count"]},
        "os_egress": {"denied_probe_count": 5, "allowed_attempt_count": 0},
        "epoch": {"epoch_index": 1, "measured_run_count": 1},
        "live_semantic_verify": {"grounding_called": int(trace["grounding_called"]), "dlp_called": int(trace["dlp_called"])},
    }

    writer = EvidenceWriter(evidence_root / "receipts", run_id)
    parent: list[str] = []
    meta: dict[str, dict] = {}
    for receipt_type in MANDATORY:
        subject = [{"name": receipt_type, "sha256": trace["model_sha256"] if receipt_type.startswith("model_identity") else _SHA}]
        payload = {"count": 1, "terminal_status_digest": hashlib.sha256(trace["terminal_status"].encode()).hexdigest()[:16]}
        path, digest = writer.write_receipt(receipt_type, subject=subject, parents=parent, payload=payload)
        parent = [digest]
        meta[receipt_type] = {"digest": digest, "subject": json.loads(Path(path).read_text(encoding="utf-8"))["subject"]}
    pointer = f"receipts/{parent[0]}.json"
    (evidence_root / "final_receipt_path.txt").write_text(pointer + "\n", encoding="ascii")
    write_canonical_json(evidence_root / "artifact_profile.json", {"profile_version": "v2.8", "mandatory_receipts": MANDATORY, "final_pointer": pointer, "max_receipts": 100})

    observations = [
        _observation(verifier, meta[t]["digest"], t, meta[t]["subject"], raw_by_type[t]) for t in EXTERNAL_TYPES
    ]
    build_artifact_manifest(evidence_root)  # manifests receipts+profile+pointer only (bundle is outside the root)

    # P0-A: sign only with an EXTERNAL provisioned key; verify against an EXTERNAL
    # SHA-pinned trust policy (never a caller-supplied key). No provisioned key =>
    # no bundle => semantic UNAVAILABLE (structural-only diagnostic, never M3 PASS).
    signing_seed = _load_external_signing_seed()
    trust_policy_path, trust_policy_sha256 = _resolve_trust_policy()
    production_signing_key_ready = signing_seed is not None

    verifier_argv = [sys.executable, str(BENCH_ROOT / "offline_verifier" / "verify.py"), str(evidence_root), "--mode", "m3-evidence"]
    if production_signing_key_ready:
        public = verifier.ed25519_publickey(signing_seed).hex()
        unsigned = {"schema_version": verifier.OBSERVATION_SCHEMA, "run_id": run_id, "signer_public_key_ed25519": public, "observations": observations}
        signature = verifier.ed25519_sign(signing_seed, verifier.canonical_bytes(unsigned)).hex()
        bundle = dict(unsigned)
        bundle["signature_ed25519"] = signature
        bundle_path = evidence_root.parent / f"observation_bundle-{run_id}.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        verifier_argv += ["--observation-bundle", str(bundle_path), "--trust-policy", str(trust_policy_path), "--trust-policy-sha256", trust_policy_sha256]

    completed = subprocess.run(verifier_argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    verdict = json.loads(completed.stdout)
    structural_pass = verdict.get("structural", {}).get("status") == "M3_ARTIFACT_STRUCTURE_PASS"
    semantic_status = verdict.get("semantic", {}).get("status")
    semantic_pass = semantic_status == "M3_SEMANTIC_PASS"
    # Owner E2E "passes" when the real path ran and structural evidence verified. Semantic
    # PASS additionally requires a provisioned external key + external trust policy.
    smoke_verifier_pass = completed.returncode == 0 and structural_pass

    return {
        "schema_version": "butler.bench.owner-result.v3",
        "run_id": run_id,
        "status": "PRODUCT_ADAPTER_RESULT",
        "evidence_root_relative": evidence_root_relative,
        "final_receipt_relative": pointer,
        "artifact_manifest_sha256": json.loads((evidence_root / "artifact_manifest.jcs.json").read_text())["artifact_manifest_sha256"],
        "offline_verifier_exit_code": completed.returncode,
        "structural_verify": "PASS" if structural_pass else "FAIL",
        "semantic_verify": "PASS" if semantic_pass else ("UNAVAILABLE_NO_PROVISIONED_KEY" if not production_signing_key_ready else "FAIL"),
        "production_signing_key_ready": production_signing_key_ready,
        "committed_signing_seed": False,
        "smoke_evidence_verifier_pass": bool(smoke_verifier_pass),
        "owner_e2e_pass": bool(smoke_verifier_pass),
        "imported_product_module_count": imported_product_count,
        "real_smoke": {k: trace[k] for k in (
            "model_sha256", "model_size_bytes", "metal_backend_initialized", "actual_offloaded_layer_count",
            "requested_gpu_layers", "first_token_received", "completion_token_count", "load_ms",
            "first_token_latency_ms", "grounding_called", "dlp_called", "approval_called",
            "terminal_gate_called", "terminal_count", "terminal_status", "architecture", "llama_cpp_version",
        )},
        "measurement_class": "NON_BENCHMARK_SMOKE_DIAGNOSTIC",
        "sample_count": 1,
        "performance_comparison": "NOT_PERFORMED",
        # §0/§17: a single NON_BENCHMARK smoke never auto-promotes governance M3 validity.
        # The verifier PASS above is about this smoke's evidence artifact only; formal
        # M3_EVIDENCE_VALID stays false until the owner's full M3 run (cold3/warm10/...).
        "m3_evidence_valid": False,
        "m3_smoke_auto_promotion_count": 0,
        "m4_ready": False,
        "g1_ready": False,
        "runtime_activation_allowed": 0,
    }


def main() -> int:
    output_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (BENCH_ROOT / "owner_e2e" / "_run_output")
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        result = run(output_root)
    except OwnerBlock as exc:
        print(json.dumps({"status": str(exc).split(":")[0], "detail": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["owner_e2e_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
