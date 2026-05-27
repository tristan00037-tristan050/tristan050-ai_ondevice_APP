from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import platform as _platform
import sys
from typing import Any

REQUIRED_RUNTIME_MODULES = {"mlx_lm": "mlx_lm", "peft": "peft", "transformers": "transformers"}
PACKAGE_DISTRIBUTIONS = {"mlx_lm": "mlx-lm", "peft": "peft", "transformers": "transformers"}


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _package_version(distribution_name: str) -> str | None:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def detect_runtime_packages() -> dict[str, Any]:
    packages = {key: _module_available(module) for key, module in REQUIRED_RUNTIME_MODULES.items()}
    runtime_available = all(packages.values())
    return {
        "schema_version": "box2.helper3.runtime.v3",
        "runtime_available": runtime_available,
        "runtime_packages": packages,
        "package_versions": {key: _package_version(PACKAGE_DISTRIBUTIONS[key]) for key in REQUIRED_RUNTIME_MODULES},
        "python_version": sys.version.split()[0],
        "platform": _platform.platform(),
        "fail_class": None if runtime_available else "PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED",
    }


def load_runtime() -> dict[str, Any]:
    detected = detect_runtime_packages()
    if not detected["runtime_available"]:
        return detected
    imported: dict[str, bool] = {}
    try:
        for key, module_name in REQUIRED_RUNTIME_MODULES.items():
            importlib.import_module(module_name)
            imported[key] = True
    except Exception as exc:  # pragma: no cover
        # Codex P2 (PR #755): str(exc) from native loader failures can carry
        # local paths and environment details into evidence, violating the
        # repo's meta-only/no-raw-output rule. Mirror the real-load path
        # (real_load_smoke.py) by keeping only error_class plus a digest.
        detected.update({
            "runtime_available": False,
            "runtime_packages": {**detected["runtime_packages"], **imported},
            "fail_class": "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR",
            "error_class": exc.__class__.__name__,
            "error_message_digest": "sha256:" + _sha256_text(str(exc)),
        })
        return detected
    detected.update({"runtime_available": True, "runtime_packages": {key: True for key in REQUIRED_RUNTIME_MODULES}, "fail_class": None})
    return detected
