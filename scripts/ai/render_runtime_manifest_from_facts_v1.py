#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

try:
    from .common_pack_build_v1 import read_json, sha256_file, write_json, safe_print_kv, require_file
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import read_json, sha256_file, write_json, safe_print_kv, require_file


PACK_DIR = Path("packs/micro_default")


def main() -> None:
    require_file(PACK_DIR / "tokenizer.json")
    require_file(PACK_DIR / "config.json")
    require_file(PACK_DIR / "chat_template.jinja")

    tokenizer_digest = sha256_file(PACK_DIR / "tokenizer.json")
    chat_template_digest = sha256_file(PACK_DIR / "chat_template.jinja")
    config_digest = sha256_file(PACK_DIR / "config.json")

    weights_digest = "PENDING_REAL_WEIGHTS"
    if (PACK_DIR / "model.onnx").exists():
        weights_digest = sha256_file(PACK_DIR / "model.onnx")

    manifest = {
        "schema_version": 1,
        "logical_pack_id": "micro_default",
        "model_format": "onnx",
        "model_type": "qwen2",
        "quantization_mode": "weight_only_int4",
        "context_length": 8192,
        "bos_token_id": None,
        "eos_token_id": None,
        "pad_token_id": None,
        "external_data_shards_allowed": True,
        "graph_io_contract": {},
        "search_defaults": {
            "do_sample": False,
            "num_beams": 1,
            "top_k": 1,
            "top_p": 1.0,
            "temperature": 1.0,
        },
        "artifacts": {
            "weights_digest_sha256": weights_digest,
            "tokenizer_digest_sha256": tokenizer_digest,
            "chat_template_digest_sha256": chat_template_digest,
            "config_digest_sha256": config_digest,
        },
        "status": "pending_real_weights",
    }
    write_json(PACK_DIR / "runtime_manifest.json", manifest)
    safe_print_kv("RUNTIME_MANIFEST_RENDERED", "1")


if __name__ == "__main__":
    main()
