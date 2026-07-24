#!/usr/bin/env python3
"""Verify a production BUILD_CONTEXT without consulting Git."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_trust import build_context_digest, strict_json_loads, validate_build_context


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path)
    arguments = parser.parse_args()
    try:
        metadata = arguments.context.lstat()
        if arguments.context.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024:
            raise RuntimeError("BUILD_CONTEXT_TYPE_INVALID")
        document = strict_json_loads(arguments.context.read_bytes(), maximum=64 * 1024)
        validate_build_context(document)
        digest = build_context_digest(document)
    except Exception:
        print("BUILD_CONTEXT_VERIFY_OK=0 ERROR_CODE=BUILD_CONTEXT_INVALID")
        return 1
    print(json.dumps({"BUILD_CONTEXT_VERIFY_OK": 1, "digest": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
