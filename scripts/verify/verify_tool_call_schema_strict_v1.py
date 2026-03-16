#!/usr/bin/env python3
"""
verify_tool_call_schema_strict_v1.py — PR-AI-16C 독립 verifier
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def load_schema(path: str) -> dict:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    tool_map = {}
    for tool in schema.get("tools", []):
        name = tool.get("name")
        if not name:
            continue
        arg_schema = tool.get("arguments", {})
        tool_map[name] = {
            "required": set(tool.get("required", [])),
            "allowed_keys": set(arg_schema.keys()),
            "arg_schema": arg_schema,
        }
    schema["_tool_map"] = tool_map
    return schema


def validate_record(record: dict, schema: dict) -> tuple[bool, str]:
    tool_name = record.get("tool_name", "")
    registered = set(schema.get("registered_actions", []))
    tool_map = schema.get("_tool_map", {})
    if tool_name not in registered:
        return False, f"unregistered tool_name: {tool_name}"
    tool_def = tool_map.get(tool_name)
    if tool_def is None:
        return False, f"tool_def not found: {tool_name}"
    args = record.get("arguments", {})
    required = tool_def["required"]
    allowed_keys = tool_def["allowed_keys"]
    arg_schema = tool_def["arg_schema"]
    missing = required - set(args.keys())
    if missing:
        return False, f"missing required: {missing}"
    extra = set(args.keys()) - allowed_keys
    if extra:
        return False, f"extra keys: {extra}"
    for key, val in args.items():
        if key not in arg_schema:
            continue
        field = arg_schema[key]
        expected_type = field.get("type")
        if expected_type and expected_type in TYPE_MAP:
            if expected_type == "integer" and isinstance(val, bool):
                return False, f"{key}: expected integer, got bool"
            if expected_type == "boolean" and type(val) is not bool:
                return False, f"{key}: expected boolean, got {type(val).__name__}"
            if expected_type == "integer" and type(val) is not int:
                return False, f"{key}: expected integer, got {type(val).__name__}"
            if expected_type not in {"integer", "boolean"} and not isinstance(val, TYPE_MAP[expected_type]):
                return False, f"{key}: expected {expected_type}, got {type(val).__name__}"
        if isinstance(val, str) and val.strip() == "":
            return False, f"{key}: empty string not allowed"
        allowed_enum = field.get("enum")
        if allowed_enum and val not in allowed_enum:
            return False, f"{key}: '{val}' not in enum {allowed_enum}"
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in field and val < field["minimum"]:
                return False, f"{key}: {val} < minimum {field['minimum']}"
            if "maximum" in field and val > field["maximum"]:
                return False, f"{key}: {val} > maximum {field['maximum']}"
    return True, "ok"


def main() -> None:
    ap = argparse.ArgumentParser(description="tool_call schema strict verifier")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--data", required=True)
    args = ap.parse_args()
    schema = load_schema(args.schema)
    total = 0
    passed = 0
    errors = []
    with open(args.data, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                errors.append(f"line {i}: JSON parse error")
                continue
            completion = row.get("completion", "{}")
            try:
                record = json.loads(completion) if isinstance(completion, str) else completion
            except Exception:
                errors.append(f"line {i}: completion JSON parse error")
                total += 1
                continue
            total += 1
            ok, reason = validate_record(record, schema)
            if ok:
                passed += 1
            else:
                errors.append(f"line {i}: FAIL — {reason}")
    schema_pass_rate = round(passed / total, 4) if total > 0 else 0.0
    print(f"total={total} passed={passed} schema_pass_rate={schema_pass_rate}")
    for e in errors[:10]:
        print(f"  {e}", file=sys.stderr)
    if schema_pass_rate < 1.0:
        print("TOOL_CALL_JSONSCHEMA_STRICT_OK=0")
        sys.exit(1)
    print("TOOL_CALL_JSONSCHEMA_STRICT_OK=1")
    print("TOOL_CALL_ARGUMENT_TYPE_ENFORCED_OK=1")
    print("TOOL_CALL_ARGUMENT_RANGE_ENUM_ENFORCED_OK=1")
    sys.exit(0)


if __name__ == "__main__":
    main()
