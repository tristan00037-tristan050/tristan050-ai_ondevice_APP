#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "contracts/assets/llama-cpp-python.lock.json"
SBOM_PATH = ROOT / "contracts/assets/asset-runtime-sbom.cdx.json"
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def _fail(code: str) -> int:
    print("ASSET_RUNTIME_SUPPLY_CHAIN_OK=0")
    print(f"ERROR_CODE={code}")
    return 1


def main() -> int:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        sbom = json.loads(SBOM_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _fail("ASSET_RUNTIME_LOCK_INVALID")
    expected_lock_keys = {
        "schema_version",
        "package",
        "version",
        "embedded_llama_cpp_commit",
        "minimum_security_build",
        "advisory",
        "cve",
    }
    if (
        not isinstance(lock, dict)
        or set(lock) != expected_lock_keys
        or lock["schema_version"] != 1
        or lock["package"] != "llama-cpp-python"
        or not isinstance(lock["version"], str)
        or not VERSION_RE.fullmatch(lock["version"])
        or not isinstance(lock["embedded_llama_cpp_commit"], str)
        or not COMMIT_RE.fullmatch(lock["embedded_llama_cpp_commit"])
        or lock["minimum_security_build"] != "b7824"
        or lock["advisory"] != "GHSA-96jg-mvhq-q7q7"
        or lock["cve"] != "CVE-2026-33298"
    ):
        return _fail("ASSET_RUNTIME_LOCK_INVALID")
    version = lock["version"]
    commit = lock["embedded_llama_cpp_commit"]
    required_pin = f"llama-cpp-python=={version}"
    required_files = (
        ROOT / "requirements-serving.txt",
        ROOT / "scripts/build_complete_app.sh",
        ROOT / "scripts/build_runtime.sh",
        ROOT / ".github/workflows/box4-box6-activation.yml",
    )
    try:
        if any(
            required_pin not in path.read_text(encoding="utf-8")
            for path in required_files
        ):
            return _fail("ASSET_RUNTIME_PIN_DRIFT")
    except (OSError, UnicodeError):
        return _fail("ASSET_RUNTIME_PIN_DRIFT")
    components = sbom.get("components") if isinstance(sbom, dict) else None
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.6"
        or not isinstance(components, list)
    ):
        return _fail("ASSET_RUNTIME_SBOM_INVALID")
    matches = [
        item
        for item in components
        if isinstance(item, dict) and item.get("name") == "llama-cpp-python"
    ]
    if len(matches) != 1:
        return _fail("ASSET_RUNTIME_SBOM_INVALID")
    component = matches[0]
    properties = {
        item.get("name"): item.get("value")
        for item in component.get("properties", [])
        if isinstance(item, dict)
    }
    if (
        component.get("version") != version
        or component.get("purl") != f"pkg:pypi/llama-cpp-python@{version}"
        or properties.get("butler:embedded-llama-cpp-commit") != commit
        or properties.get("butler:minimum-security-build") != "b7824"
        or properties.get("butler:security-advisory") != "GHSA-96jg-mvhq-q7q7"
    ):
        return _fail("ASSET_RUNTIME_SBOM_DRIFT")
    print("ASSET_RUNTIME_SUPPLY_CHAIN_OK=1")
    print("ERROR_CODE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
