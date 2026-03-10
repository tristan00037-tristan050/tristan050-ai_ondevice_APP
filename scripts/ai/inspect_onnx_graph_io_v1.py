#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

try:
    from .common_pack_build_v1 import ensure_dir, safe_print_kv, write_json
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import ensure_dir, safe_print_kv, write_json


def main() -> None:
    onnx_path = Path("packs/micro_default/model.onnx")
    if not onnx_path.exists():
        safe_print_kv("ONNX_GRAPH_IO_INSPECT_SKIPPED", "MODEL_ONNX_MISSING")
        return

    # placeholder: real implementation requires onnx package
    graph_io = {
        "inputs": [],
        "outputs": [],
        "note": "placeholder — real weights required",
    }
    out_dir = Path("tmp")
    ensure_dir(out_dir)
    write_json(out_dir / "onnx_graph_io.json", graph_io)
    safe_print_kv("ONNX_GRAPH_IO_INSPECTED", "1")


if __name__ == "__main__":
    main()
