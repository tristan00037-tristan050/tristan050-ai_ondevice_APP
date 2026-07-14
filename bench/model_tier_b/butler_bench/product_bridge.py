from __future__ import annotations

import importlib
import inspect
import re
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

from .canonical import canonical_sha256, sha256_file
from .errors import ExitCode, FailClass, GateError

REQUIRED_ENTRYPOINTS = (
    "Box3ProductPipelineRuntime",
    "run_product_matrix",
    "run_cold_worker_handshake",
    "measure_dual_resident_pressure",
    "verify_samples_first",
)
ADAPTER_ENTRYPOINT = "butler_bench_run_v2"
_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_product_module(
    module_name: str,
    *,
    approved_product_root: Path,
    expected_module_sha256: str,
    expected_commit_oid: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,255}", module_name) or module_name.startswith(("tests.", "test_", "mocks.")):
        _block("PRODUCT_MODULE_NAME")
    if not _SHA256.fullmatch(expected_module_sha256) or not _OID.fullmatch(expected_commit_oid):
        _block("PRODUCT_EXPECTED_IDENTITY")
    root = approved_product_root.resolve(strict=True)
    try:
        module = importlib.import_module(module_name)
    except Exception:
        _block("PRODUCT_IMPORT_FAILED")
    module_path = _module_file(module)
    if root not in module_path.parents or {part.casefold() for part in module_path.parts} & {"tests", "test", "fixtures", "mocks"}:
        _block("PRODUCT_MODULE_PATH")
    if sha256_file(module_path) != expected_module_sha256:
        _block("PRODUCT_MODULE_DIGEST")
    if getattr(module, "__butler_product_commit_oid__", None) != expected_commit_oid:
        _block("PRODUCT_COMMIT_BINDING")
    # F-004: do not trust the module-internal commit constant alone. Prove via git
    # plumbing that the on-disk module blob is actually the blob recorded for this
    # path in the approved commit tree (git cat-file / ls-tree / rev-parse).
    blob_binding = verify_blob_in_commit_tree(module_path, expected_commit_oid)
    entrypoints: list[dict[str, str]] = []
    for name in (*REQUIRED_ENTRYPOINTS, ADAPTER_ENTRYPOINT):
        value = getattr(module, name, None)
        if not callable(value):
            _block("PRODUCT_ENTRYPOINT_MISSING")
        owner_path = Path(inspect.getsourcefile(value) or "").resolve(strict=True)
        if root not in owner_path.parents or {part.casefold() for part in owner_path.parts} & {"tests", "fixtures", "mocks"}:
            _block("PRODUCT_ENTRYPOINT_OWNER")
        entrypoints.append({"name": name, "owner_relative_path": owner_path.relative_to(root).as_posix(), "owner_sha256": sha256_file(owner_path)})
    payload = {
        "schema_version": "butler.model-tier-b.product-entrypoints.v2.8",
        "module": module.__name__,
        "module_relative_path": module_path.relative_to(root).as_posix(),
        "module_file_sha256": expected_module_sha256,
        "product_commit_oid": expected_commit_oid,
        "git_object_format": blob_binding["object_format"],
        "git_commit_tree_path": blob_binding["git_toplevel_relative_path"],
        "git_commit_tree_blob_oid": blob_binding["commit_tree_blob_oid"],
        "entrypoints": entrypoints,
        "runtime_activation_allowed": 0,
    }
    payload["product_identity_sha256"] = canonical_sha256(payload)
    return payload


def verify_blob_in_commit_tree(file_path: Path, commit_oid: str) -> dict[str, str]:
    """F-004: prove ``file_path``'s content blob is contained in ``commit_oid``'s
    tree using git plumbing, instead of trusting a module-internal constant.

    Resolves the git worktree top, confirms ``commit_oid`` is a real commit object
    whose length matches the repository object format, then compares the blob OID
    git records for the file's path in that commit (``git rev-parse
    <commit>:<path>`` cross-checked with ``git ls-tree``) against the blob OID of
    the on-disk file content (``git hash-object``). Any mismatch or git failure is
    fail-closed. Returns the verified binding for inclusion in the product identity.
    """
    resolved = file_path.resolve(strict=True)
    toplevel = Path(_git(["rev-parse", "--show-toplevel"], cwd=resolved.parent, detail="PRODUCT_GIT_TOPLEVEL")).resolve(strict=True)
    if toplevel not in resolved.parents:
        _block("PRODUCT_GIT_WORKTREE")
    object_format = _git(["rev-parse", "--show-object-format"], cwd=toplevel, detail="PRODUCT_GIT_OBJECT_FORMAT")
    expected_len = 64 if object_format == "sha256" else 40
    if not re.fullmatch(rf"[0-9a-f]{{{expected_len}}}", commit_oid):
        _block("PRODUCT_COMMIT_OID_FORMAT")
    if _git(["cat-file", "-t", commit_oid], cwd=toplevel, detail="PRODUCT_COMMIT_OBJECT") != "commit":
        _block("PRODUCT_COMMIT_OBJECT")
    relative = resolved.relative_to(toplevel).as_posix()
    tree_blob = _git(["rev-parse", "--verify", f"{commit_oid}:{relative}"], cwd=toplevel, detail="PRODUCT_BLOB_NOT_IN_TREE")
    file_blob = _git(["hash-object", str(resolved)], cwd=toplevel, detail="PRODUCT_BLOB_HASH")
    if not re.fullmatch(rf"[0-9a-f]{{{expected_len}}}", tree_blob) or tree_blob != file_blob:
        _block("PRODUCT_COMMIT_TREE_MISMATCH")
    ls_tree = _git(["ls-tree", "--full-tree", commit_oid, "--", relative], cwd=toplevel, detail="PRODUCT_LS_TREE").split()
    if len(ls_tree) < 3 or ls_tree[1] != "blob" or ls_tree[2] != tree_blob:
        _block("PRODUCT_COMMIT_TREE_MISMATCH")
    return {"git_toplevel_relative_path": relative, "commit_tree_blob_oid": tree_blob, "object_format": object_format}


def _git(args: list[str], *, cwd: Path, detail: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        _block("PRODUCT_GIT_UNAVAILABLE")
    if completed.returncode != 0:
        _block(detail)
    return completed.stdout.strip()


def verify_integration_evidence(evidence: dict[str, Any], product_identity_sha256: str) -> str:
    keys = {
        "schema_version", "product_identity_sha256", "production_import_path",
        "entrypoint_call_counts", "production_gate_event_count", "observer_trace_sha256",
        "coverage_artifact_sha256", "route_diff_sha256", "route_semantics_changed",
        "runtime_activation_allowed", "integration_subject_sha256",
    }
    if set(evidence) != keys or evidence["schema_version"] != "butler.model-tier-b.actual-integration.v2.8":
        _block("INTEGRATION_EVIDENCE_KEYS")
    unsigned = {key: value for key, value in evidence.items() if key != "integration_subject_sha256"}
    if canonical_sha256(unsigned) != evidence["integration_subject_sha256"]:
        _block("INTEGRATION_EVIDENCE_DIGEST")
    if evidence["product_identity_sha256"] != product_identity_sha256:
        _block("INTEGRATION_PRODUCT_IDENTITY")
    counts = evidence["entrypoint_call_counts"]
    required = set(REQUIRED_ENTRYPOINTS) | {ADAPTER_ENTRYPOINT}
    if not isinstance(counts, dict) or set(counts) != required or any(type(value) is not int or value < 1 for value in counts.values()):
        _block("INTEGRATION_ENTRYPOINT_COVERAGE")
    if type(evidence["production_gate_event_count"]) is not int or evidence["production_gate_event_count"] < len(REQUIRED_ENTRYPOINTS):
        _block("PRODUCTION_GATE_EVENTS")
    for key in ("observer_trace_sha256", "coverage_artifact_sha256", "route_diff_sha256"):
        if not isinstance(evidence[key], str) or not _SHA256.fullmatch(evidence[key]):
            _block("INTEGRATION_DIGEST")
    if evidence["route_semantics_changed"] is not False or evidence["runtime_activation_allowed"] != 0:
        _block("ROUTE_OR_ACTIVATION")
    return evidence["integration_subject_sha256"]


def load_product_module(module_name: str, **identity: Any) -> ModuleType:
    validate_product_module(module_name, **identity)
    return importlib.import_module(module_name)


def _module_file(module: ModuleType) -> Path:
    raw = getattr(module, "__file__", None)
    if not raw:
        _block("PRODUCT_MODULE_FILE")
    try:
        return Path(raw).resolve(strict=True)
    except OSError:
        _block("PRODUCT_MODULE_FILE")


def _block(detail: str) -> None:
    raise GateError(FailClass.PRODUCT_GATE, detail, exit_code=ExitCode.PROTOCOL)
