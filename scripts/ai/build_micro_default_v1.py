#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PACK_DIR = Path("packs/micro_default")
PACK_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_runtime_manifest(
    *,
    model_type: str,
    bos_token_id: int | None,
    eos_token_id: int | list[int] | None,
    pad_token_id: int | None,
    graph_io_contract: dict[str, Any],
    weights_digest: str,
    tokenizer_digest: str,
    chat_template_digest: str,
    config_digest: str,
    status: str,
) -> None:
    manifest = {
        "schema_version": 1,
        "logical_pack_id": "micro_default",
        "model_format": "onnx",
        "model_type": model_type,
        "quantization_mode": "weight_only_int4",
        "context_length": 8192,
        "bos_token_id": bos_token_id,
        "eos_token_id": eos_token_id,
        "pad_token_id": pad_token_id,
        "external_data_shards_allowed": True,
        "graph_io_contract": graph_io_contract,
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
        "status": status,
    }
    (PACK_DIR / "runtime_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_sha256sums() -> None:
    files = [
        "model.onnx",
        "tokenizer.json",
        "config.json",
        "chat_template.jinja",
        "runtime_manifest.json",
    ]
    if (PACK_DIR / "model.onnx.data").exists():
        files.insert(1, "model.onnx.data")

    lines = []
    for name in files:
        digest = sha256_file(PACK_DIR / name)
        lines.append(f"{digest}  {name}")
    (PACK_DIR / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print("build_micro_default_v1.py prepared")
