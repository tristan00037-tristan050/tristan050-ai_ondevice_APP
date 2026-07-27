from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

V9_2_R2B_MODEL_NAME = "butler-1.7b-v9-2-r2b-q4_k_m.gguf"
V9_2_R2B_Q4_SHA256_FULL = "aae4ea7a4ebe0586db3317d5209b5565abcd326ea73decb7ffa99f433c218847"

FORBIDDEN_HELPER35_MARKERS = ("helper3", "helper5", "format_adapter", "tool_call_adapter")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    fail_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Box3BundleActivationReport:
    schema_version: str
    pass_ready: bool
    model_sha_match: bool
    helper35_runtime_stack_zero: bool
    helper_sdk_repo_internal_ready: bool
    helper2_embedding_ready: bool
    human_approval_ready: bool
    helper_component_guard_ready: bool
    fixed_eval_report_ready: bool
    checks: list[CheckResult]
    external_send_zero: bool = True
    raw_text_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(c) for c in self.checks]
        return data


@dataclass(frozen=True)
class BundleActivationInputs:
    model_path: Path | None = None
    models_root: Path | None = None
    helper_sdk_paths: tuple[Path, ...] = ()
    helper2_embedding_path: Path | None = None
    human_approval_path: Path | None = None
    helper_guard_path: Path | None = None
    fixed_eval_path: Path | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_exists(path: Path | None) -> bool:
    try:
        return bool(path and path.exists())
    except OSError:
        return False


def _is_under_repo_internal_sdk(path: Path, repo_root: Path) -> bool:
    try:
        resolved = path.resolve()
        internal = (repo_root / "butler_pc_core" / "cards" / "box3" / "sdk").resolve()
        return resolved == internal or internal in resolved.parents
    except OSError:
        return False


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_NOT_OBJECT")
    return value


def _check_model(path: Path | None) -> CheckResult:
    if not _safe_exists(path):
        return CheckResult("model_sha", False, "BOX3_V9_MODEL_MISSING")
    if not path or path.name != V9_2_R2B_MODEL_NAME:
        return CheckResult("model_sha", False, "BOX3_V9_MODEL_NAME_INVALID", {"model_name": path.name if path else None})
    measured = sha256_file(path)
    if measured != V9_2_R2B_Q4_SHA256_FULL:
        return CheckResult(
            "model_sha",
            False,
            "BOX3_V9_MODEL_SHA_MISMATCH",
            {"expected": V9_2_R2B_Q4_SHA256_FULL, "actual": measured},
        )
    return CheckResult("model_sha", True, details={"sha256_full": measured, "model_name": path.name})


def _check_helper35_stack_zero(
    model_path: Path | None,
    models_root: Path | None,
) -> CheckResult:
    roots = []
    if model_path is not None:
        roots.append(model_path.parent)
    if models_root is not None:
        roots.append(models_root)
    offenders: list[str] = []
    for root in roots:
        if not _safe_exists(root):
            continue
        try:
            for item in root.rglob("*.safetensors"):
                lowered = item.name.casefold()
                if any(marker in lowered for marker in FORBIDDEN_HELPER35_MARKERS):
                    offenders.append(item.name)
        except OSError:
            continue
    if offenders:
        return CheckResult("helper35_runtime_stack_zero", False, "HELPER35_RUNTIME_STACK_BUNDLE_FORBIDDEN", {"offender_count": len(offenders)})
    return CheckResult("helper35_runtime_stack_zero", True)


def _check_helper_sdk_paths(
    paths: tuple[Path, ...],
    repo_root: Path,
) -> CheckResult:
    missing: list[str] = (
        [f"helper_sdk_{index}" for index in range(len(paths), 3)]
        if len(paths) < 3
        else []
    )
    non_internal: list[str] = []
    forbidden_names: list[str] = []
    for index, path in enumerate(paths):
        key = f"helper_sdk_{index}"
        if not _safe_exists(path):
            missing.append(key)
            continue
        assert path is not None
        if not _is_under_repo_internal_sdk(path, repo_root):
            non_internal.append(key)
        lowered = str(path).casefold()
        if "helper3" in lowered or "helper5" in lowered:
            forbidden_names.append(key)
    if missing or non_internal or forbidden_names:
        return CheckResult(
            "helper_sdk_repo_internal",
            False,
            "HELPER_SDK_REPO_INTERNAL_PATH_INVALID",
            {"missing": missing, "non_internal": non_internal, "forbidden_helper35_name": forbidden_names},
        )
    return CheckResult("helper_sdk_repo_internal", True)


def _check_helper2_embedding(path: Path | None) -> CheckResult:
    if not _safe_exists(path):
        return CheckResult("helper2_embedding", False, "HELPER2_EMBEDDING_ASSET_MISSING")
    return CheckResult("helper2_embedding", True, details={"kind": "directory" if path and path.is_dir() else "file"})


def _check_json_path(path: Path | None, name: str) -> CheckResult:
    if not _safe_exists(path):
        return CheckResult(name, False, f"{name.upper()}_MISSING")
    assert path is not None
    try:
        value = _load_json(path)
    except Exception:
        return CheckResult(name, False, f"{name.upper()}_JSON_INVALID")
    return CheckResult(name, True, details={"top_level_keys": sorted(value)[:12]})


def _check_fixed_eval_report(path: Path | None) -> CheckResult:
    if not _safe_exists(path):
        return CheckResult("fixed_eval_report", False, "FIXED_EVAL_REPORT_MISSING")
    assert path is not None
    try:
        value = _load_json(path)
    except Exception:
        return CheckResult("fixed_eval_report", False, "FIXED_EVAL_REPORT_JSON_INVALID")
    unsupported = value.get("unsupported_count")
    degen = value.get("degen_detected")
    if unsupported != 0:
        return CheckResult("fixed_eval_report", False, "FIXED_EVAL_UNSUPPORTED_NONZERO", {"unsupported_count": unsupported})
    if degen is not False:
        return CheckResult("fixed_eval_report", False, "FIXED_EVAL_DEGEN_DETECTED", {"degen_detected": degen})
    return CheckResult("fixed_eval_report", True, details={"unsupported_count": unsupported, "degen_detected": degen})


def verify_box3_bundle_activation(
    repo_root: Path | None = None,
    *,
    inputs: BundleActivationInputs | None = None,
) -> Box3BundleActivationReport:
    root = (repo_root or Path.cwd()).resolve()
    supplied = inputs or BundleActivationInputs()
    checks = [
        _check_model(supplied.model_path),
        _check_helper35_stack_zero(supplied.model_path, supplied.models_root),
        _check_helper_sdk_paths(supplied.helper_sdk_paths, root),
        _check_helper2_embedding(supplied.helper2_embedding_path),
        _check_json_path(supplied.human_approval_path, "human_approval"),
        _check_json_path(supplied.helper_guard_path, "helper_component_guard"),
        _check_fixed_eval_report(supplied.fixed_eval_path),
    ]
    by_name = {c.name: c.passed for c in checks}
    pass_ready = all(c.passed for c in checks)
    return Box3BundleActivationReport(
        schema_version="box3.bundle_activation.report.v2_4",
        pass_ready=pass_ready,
        model_sha_match=by_name.get("model_sha", False),
        helper35_runtime_stack_zero=by_name.get("helper35_runtime_stack_zero", False),
        helper_sdk_repo_internal_ready=by_name.get("helper_sdk_repo_internal", False),
        helper2_embedding_ready=by_name.get("helper2_embedding", False),
        human_approval_ready=by_name.get("human_approval", False),
        helper_component_guard_ready=by_name.get("helper_component_guard", False),
        fixed_eval_report_ready=by_name.get("fixed_eval_report", False),
        checks=checks,
    )


def main() -> int:
    report = verify_box3_bundle_activation()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.pass_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
