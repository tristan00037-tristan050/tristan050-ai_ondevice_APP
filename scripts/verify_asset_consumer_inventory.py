#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "contracts/assets/consumer-inventory-v1.json"
SCHEMA = ROOT / "contracts/assets/consumer-inventory-v1.schema.json"
SCAN_ROOTS = (ROOT / "butler_pc_core", ROOT / "butler_sidecar.py")
LOADER_NAMES = {"Llama", "from_pretrained", "load_file", "safe_open"}


def _loader_files() -> set[str]:
    found: set[str] = set()
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        paths.extend(root.rglob("*.py") if root.is_dir() else [root])
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            raise RuntimeError("SOURCE_PARSE_FAILED")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr
                if isinstance(function, ast.Attribute)
                else ""
            )
            if name in LOADER_NAMES or (
                name == "load"
                and isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "torch"
            ):
                found.add(path.relative_to(ROOT).as_posix())
    return found


def main() -> int:
    try:
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(inventory)
        rows = inventory["consumers"]
        ids = [row["id"] for row in rows]
        sources = {row["source_file"] for row in rows}
        if len(ids) != len(set(ids)):
            raise RuntimeError("DUPLICATE_CONSUMER_ID")
        if any(row["migration_status"] != "MIGRATED" for row in rows):
            raise RuntimeError("CONSUMER_MIGRATION_INCOMPLETE")
        if missing := _loader_files() - sources:
            raise RuntimeError("UNINVENTORIED_LOADER:" + ",".join(sorted(missing)))
        if any(not (ROOT / source).is_file() for source in sources):
            raise RuntimeError("CONSUMER_SOURCE_MISSING")
    except Exception as exc:
        print("ASSET_CONSUMER_INVENTORY_OK=0")
        print(f"ERROR_CODE={str(exc).split(':', 1)[0]}")
        return 1
    print("ASSET_CONSUMER_INVENTORY_OK=1")
    print(f"METRIC_CONSUMER_COUNT={len(rows)}")
    print(f"METRIC_LOADER_FILE_COUNT={len(_loader_files())}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
