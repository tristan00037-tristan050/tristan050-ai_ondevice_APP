from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()[:12]
    except Exception:
        return "unknown"


def get_config_digest(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def _stage(stage_results: dict, key: str) -> dict:
    value = stage_results.get(key, {})
    return value if isinstance(value, dict) else {}


def create_manifest(
    run_mode: str,
    adapter_dir: str,
    work_dir: str,
    package_dir: str,
    version: str,
    stage_results: dict,
    elapsed_seconds: float,
    config: dict | None = None,
) -> dict:
    if run_mode not in {"dry_run", "real_run"}:
        raise ValueError("run_mode는 dry_run 또는 real_run 이어야 합니다")

    is_dry = run_mode == "dry_run"
    config = config or {}
    merge_stage = _stage(stage_results, "merge")
    onnx_stage = _stage(stage_results, "onnx")
    verify_onnx_stage = _stage(stage_results, "verify_onnx") or _stage(stage_results, "onnx_verify")
    mnn_stage = _stage(stage_results, "mnn")
    package_stage = _stage(stage_results, "package")
    ort_stage = _stage(stage_results, "ort_mobile")
    budget_stage = _stage(stage_results, "budget")

    manifest = {
        "run_mode": run_mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": get_git_sha(),
        "config_digest": get_config_digest(config),
        "version": version,
        "adapter_dir": adapter_dir,
        "work_dir": work_dir,
        "package_dir": package_dir,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "adapter_digest": None if is_dry else merge_stage.get("adapter_digest"),
        "merged_digest": None if is_dry else merge_stage.get("merged_digest"),
        "onnx_digest": None if is_dry else onnx_stage.get("onnx_digest"),
        "mnn_digest": None if is_dry else mnn_stage.get("mnn_digest"),
        "package_digest": None if is_dry else package_stage.get("pkg_digest"),
        "tokenizer_file_digests": None if is_dry else package_stage.get("tokenizer_digests"),
        "config_file_digests": None if is_dry else package_stage.get("config_digests"),
        "generation_config_digest": None if is_dry else package_stage.get("generation_config_digest"),
        "onnx_export_method": None if is_dry else onnx_stage.get("export_method"),
        "onnx_exporter_report_digests": None if is_dry else verify_onnx_stage.get("exporter_report_digests"),
        "mnn_stdout_digest": None if is_dry else mnn_stage.get("stdout_digest"),
        "mnn_stderr_digest": None if is_dry else mnn_stage.get("stderr_digest"),
        "ort_structure_verified": None if is_dry else verify_onnx_stage.get("structure_verified"),
        "ort_runtime_verified": None if is_dry else verify_onnx_stage.get("runtime_verified"),
        "external_data_file_digests": None if is_dry else verify_onnx_stage.get("external_data_digests"),
        "ort_mobile_path": None if is_dry else ort_stage.get("ort_path"),
        "ort_mobile_digest": None if is_dry else ort_stage.get("ort_digest"),
        "ort_mobile_size_mb": None if is_dry else ort_stage.get("size_mb"),
        "budget_spec": None if is_dry else budget_stage.get("budget_spec"),
        "budget_result": None if is_dry else budget_stage.get("result"),
        "elapsed_seconds": float(elapsed_seconds),
        "stage_results": stage_results,
    }

    Path("tmp").mkdir(exist_ok=True)
    output = Path("tmp") / "conversion_manifest.json"
    output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"매니페스트 저장: {output}")
    return manifest
