#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, re, sys
from pathlib import Path

FORBIDDEN_STRUCTURED_KEYS = {"raw_content", "raw_prompt", "prompt", "raw_user_text", "user_text", "original_text", "training_input_text", "transformed_text", "raw_log", "raw_path", "ip_address", "hostname", "device_id"}
ALLOWED_KEYS = {"hostname_digest", "device_id_digest", "raw_hostname_recorded", "raw_ip_recorded", "raw_device_id_recorded", "raw_prompt_recorded", "raw_user_text_recorded", "raw_log_recorded", "raw_path_recorded"}
SKIP_DIRS = {".git", "__pycache__"}
TEXT_EXTS = {".json", ".py"}

def scan_json(obj, path, errors):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            if key in FORBIDDEN_STRUCTURED_KEYS and key not in ALLOWED_KEYS:
                errors.append(f"forbidden structured key {path}.{k}")
            scan_json(v, f"{path}.{k}", errors)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_json(v, f"{path}[{i}]", errors)

def scan_python_strings(path: Path, errors):
    # Allow documentation strings mentioning policy. Disallow assignments or dict keys that persist raw values.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    k = key.value.lower()
                    if k in FORBIDDEN_STRUCTURED_KEYS and k not in ALLOWED_KEYS:
                        errors.append(f"forbidden python dict key {path}:{node.lineno}:{key.value}")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    errors = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        rel = path.relative_to(root)
        try:
            if path.suffix.lower() == ".json":
                scan_json(json.loads(path.read_text(encoding="utf-8")), str(rel), errors)
            elif path.suffix.lower() == ".py":
                scan_python_strings(path, errors)
        except Exception as exc:
            errors.append(f"scan error {rel}: {exc}")
    if errors:
        for e in errors:
            print(f"RAW_CONTENT_SCAN_FAIL {e}", file=sys.stderr)
        return 2
    print("RAW_CONTENT_SCAN_OK")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
