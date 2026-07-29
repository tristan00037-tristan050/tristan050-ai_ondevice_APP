from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--junitxml", required=True, type=Path)
    parser.add_argument("--file", action="append", required=True)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise SystemExit("REQUIRED_MANIFEST_INVALID")
    files = set(options.file)
    nodes = [
        f"{entry['file']}::{entry['title']}"
        for entry in manifest["tests"]
        if entry["runner"] == "pytest"
        and entry["platform"] == options.platform
        and entry["file"] in files
        and entry["required"] is True
    ]
    if not nodes or len(nodes) != len(set(nodes)):
        raise SystemExit("REQUIRED_PYTEST_SELECTION_INVALID")
    options.junitxml.parent.mkdir(parents=True, exist_ok=True)
    return pytest.main(["-q", *nodes, f"--junitxml={options.junitxml}"])


if __name__ == "__main__":
    raise SystemExit(main())
