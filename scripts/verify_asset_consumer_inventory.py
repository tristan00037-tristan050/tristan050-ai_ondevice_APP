#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "contracts/assets/consumer-inventory-v2.json"
SCHEMA = ROOT / "contracts/assets/consumer-inventory-v2.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts/assets/inventory-binding-receipt-v1.schema.json"
PYTHON_ROOTS = (ROOT / "butler_pc_core", ROOT / "butler_sidecar.py")
RUST_ROOT = ROOT / "butler-desktop/src-tauri/src"
MODEL_LOADER_MODULES = {"llama_cpp", "transformers", "peft", "mlx_lm"}
ALLOWED_LLAMA_IMPORT = "butler_pc_core/inference/verified_model_loader.py"
OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


@dataclass(frozen=True)
class ScanResult:
    python_model_loader_imports: tuple[str, ...]
    native_command_sources: tuple[str, ...]

    def canonical(self) -> bytes:
        return json.dumps(
            {
                "native_command_sources": list(self.native_command_sources),
                "python_model_loader_imports": list(self.python_model_loader_imports),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _python_paths() -> Iterable[Path]:
    for root in PYTHON_ROOTS:
        if root.is_dir():
            yield from root.rglob("*.py")
        else:
            yield root


def _model_loader_imports(path: Path, tree: ast.AST) -> bool:
    aliases: set[str] = set()
    direct_loader_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in MODEL_LOADER_MODULES:
                    aliases.add(alias.asname or root)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root not in MODEL_LOADER_MODULES:
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in {
                    "Llama",
                    "AutoModel",
                    "AutoModelForCausalLM",
                    "PeftModel",
                    "load",
                }:
                    direct_loader_names.add(local)
                aliases.add(local)
    if direct_loader_names:
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in direct_loader_names:
            return True
        if isinstance(function, ast.Attribute):
            if (
                isinstance(function.value, ast.Name)
                and function.value.id in aliases
                and function.attr
                in {"Llama", "from_pretrained", "load", "load_model", "load_adapter"}
            ):
                return True
            if function.attr in {"from_pretrained", "load_model", "load_adapter"}:
                return True
    return False


def scan_consumers() -> ScanResult:
    loader_sources: set[str] = set()
    for path in _python_paths():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise RuntimeError("SOURCE_PARSE_FAILED") from exc
        if _model_loader_imports(path, tree):
            loader_sources.add(path.relative_to(ROOT).as_posix())

    native_commands: set[str] = set()
    for path in RUST_ROOT.rglob("*.rs"):
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("SOURCE_PARSE_FAILED") from exc
        if "Command::new(" in raw:
            native_commands.add(path.relative_to(ROOT).as_posix())
    return ScanResult(tuple(sorted(loader_sources)), tuple(sorted(native_commands)))


def _defined_symbols(path: Path) -> set[str]:
    if path.suffix == ".py":
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        symbols: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.add(node.name)
            elif isinstance(node, ast.ClassDef):
                symbols.add(node.name)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.add(f"{node.name}.{child.name}")
        return symbols
    raw = path.read_text(encoding="utf-8")
    return set(re.findall(r"\b(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)", raw))


def audit_inventory() -> tuple[dict[str, object], ScanResult]:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(inventory)
    rows = inventory["consumers"]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("DUPLICATE_CONSUMER_ID")
    sources = {row["source_path"] for row in rows}
    for row in rows:
        source = ROOT / row["source_path"]
        if not source.is_file():
            raise RuntimeError("CONSUMER_SOURCE_MISSING")
        if row["symbol"] not in _defined_symbols(source):
            raise RuntimeError("CONSUMER_SYMBOL_MISSING")
        test_path = ROOT / row["test_node_id"].split("::", 1)[0]
        if not test_path.is_file():
            raise RuntimeError("CONSUMER_TEST_MISSING")

    scan = scan_consumers()
    if set(scan.python_model_loader_imports) != {ALLOWED_LLAMA_IMPORT}:
        raise RuntimeError("UNINVENTORIED_MODEL_LOADER")
    if not set(scan.python_model_loader_imports) <= sources:
        raise RuntimeError("UNINVENTORIED_MODEL_LOADER")
    if not set(scan.native_command_sources) <= sources:
        raise RuntimeError("UNINVENTORIED_NATIVE_CHILD")
    return inventory, scan


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not OID_RE.fullmatch(value):
        raise RuntimeError("GIT_IDENTITY_UNAVAILABLE")
    return value


def _oid(value: str) -> dict[str, str]:
    return {"algorithm": "sha1" if len(value) == 40 else "sha256", "hex": value}


def main() -> int:
    try:
        inventory, scan = audit_inventory()
        external_head = os.environ.get("GITHUB_SHA", "")
        head = _git("rev-parse", "HEAD")
        tree = _git("rev-parse", "HEAD^{tree}")
        if not OID_RE.fullmatch(external_head) or external_head != head:
            raise RuntimeError("CI_HEAD_MISMATCH")
        receipt = {
            "schema_version": 1,
            "run_id": str(uuid.uuid4()),
            "head_oid": _oid(head),
            "tree_oid": _oid(tree),
            "inventory_sha256": _sha256(
                json.dumps(
                    inventory,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ),
            "verifier_sha256": _sha256(Path(__file__).read_bytes()),
            "scan_result_sha256": _sha256(scan.canonical()),
            "result": "ALLOW",
        }
        receipt_schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(receipt_schema).validate(receipt)
        destination = os.environ.get("ASSET_INVENTORY_RECEIPT_OUT")
        if destination:
            target = Path(destination)
            if not target.is_absolute():
                raise RuntimeError("RECEIPT_PATH_INVALID")
            target.write_text(
                json.dumps(receipt, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
                + "\n",
                encoding="ascii",
            )
    except Exception as exc:
        print("ASSET_CONSUMER_INVENTORY_OK=0")
        print(f"ERROR_CODE={str(exc).split(':', 1)[0]}")
        return 1
    print("ASSET_CONSUMER_INVENTORY_OK=1")
    print(f"METRIC_CONSUMER_COUNT={len(inventory['consumers'])}")
    print(f"METRIC_MODEL_LOADER_SOURCE_COUNT={len(scan.python_model_loader_imports)}")
    print(f"METRIC_NATIVE_CHILD_SOURCE_COUNT={len(scan.native_command_sources)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
