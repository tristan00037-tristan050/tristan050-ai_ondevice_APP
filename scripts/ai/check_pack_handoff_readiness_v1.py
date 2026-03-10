#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

try:
    from .common_pack_build_v1 import read_json, require_file, safe_print_kv
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import read_json, require_file, safe_print_kv


PACK_DIR = Path("packs/micro_default")

REQUIRED_ARTIFACTS = [
    "model.onnx",
    "tokenizer.json",
    "config.json",
    "chat_template.jinja",
    "runtime_manifest.json",
    "SHA256SUMS",
]


def main() -> None:
    missing = []
    for name in REQUIRED_ARTIFACTS:
        path = PACK_DIR / name
        if not path.exists():
            missing.append(name)

    if missing:
        raise SystemExit(f"PACK_HANDOFF_NOT_READY:MISSING={','.join(missing)}")

    manifest = read_json(PACK_DIR / "runtime_manifest.json")
    if manifest.get("status") != "verified":
        safe_print_kv("PACK_HANDOFF_STATUS_WARNING", manifest.get("status", "UNKNOWN"))

    safe_print_kv("PACK_HANDOFF_READINESS_OK", "1")


if __name__ == "__main__":
    main()
