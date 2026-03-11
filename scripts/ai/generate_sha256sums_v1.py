#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

try:
    from .common_pack_build_v1 import sha256_file, safe_print_kv
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import sha256_file, safe_print_kv


REQUIRED_FILES = [
    "model.onnx",
    "tokenizer.json",
    "config.json",
    "chat_template.jinja",
    "runtime_manifest.json",
]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir", default="packs/micro_default")
    args = parser.parse_args()
    pack_dir = Path(args.pack_dir)

    files = list(REQUIRED_FILES)
    if (pack_dir / "model.onnx.data").exists():
        files.insert(1, "model.onnx.data")

    lines = []
    for name in files:
        path = pack_dir / name
        if not path.exists():
            raise SystemExit(f"SHA256SUMS_SOURCE_FILE_MISSING:{name}")
        lines.append(f"{sha256_file(path)}  {name}")

    (pack_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    safe_print_kv("SHA256SUMS_WRITTEN", "1")


if __name__ == "__main__":
    main()
