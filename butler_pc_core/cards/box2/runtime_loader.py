from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import platform as _platform
import subprocess
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


def _probe_module_import(module_name: str, *, timeout_seconds: int = 30) -> dict[str, Any]:
    """Import a runtime module in a child process.

    Some native runtime packages can abort the Python process during import
    before a Python exception can be caught. Keep contract tests alive by
    probing imports out-of-process and persisting only meta status.
    """
    command = [
        sys.executable,
        "-c",
        "import importlib, sys; importlib.import_module(sys.argv[1])",
        module_name,
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "error_class": "TimeoutExpired"}
    return {"ok": completed.returncode == 0, "returncode": completed.returncode, "error_class": None}


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
    import_results = {key: _probe_module_import(module_name) for key, module_name in REQUIRED_RUNTIME_MODULES.items()}
    imported = {key: bool(result["ok"]) for key, result in import_results.items()}
    if not all(imported.values()):
        first_error_class = next((result["error_class"] for result in import_results.values() if result["error_class"]), "SubprocessImportFailed")
        detected.update({
            "runtime_available": False,
            "runtime_packages": imported,
            "fail_class": "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR",
            "error_class": first_error_class,
            "import_returncodes": {key: result["returncode"] for key, result in import_results.items()},
        })
        return detected
    detected.update({"runtime_available": True, "runtime_packages": {key: True for key in REQUIRED_RUNTIME_MODULES}, "fail_class": None})
    return detected
