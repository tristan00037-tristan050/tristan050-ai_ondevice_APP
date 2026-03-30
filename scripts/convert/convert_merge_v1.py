from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

from scripts.convert import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_STRUCTURE,
    ConversionStageError,
    StructureOrInputError,
)


DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3-4B"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_adapter_config(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StructureOrInputError(f"adapter_config.json 파싱 실패: {exc}") from exc


def merge(adapter_dir: str, output_dir: str) -> dict:
    adapter_path = Path(adapter_dir)
    output_path = Path(output_dir)

    adapter_model = adapter_path / "adapter_model.safetensors"
    adapter_config = adapter_path / "adapter_config.json"

    if not adapter_model.exists():
        raise StructureOrInputError("adapter_model.safetensors 없음")
    if not adapter_config.exists():
        raise StructureOrInputError("adapter_config.json 없음")

    cfg = _load_adapter_config(adapter_config)
    base_model_id = cfg.get("base_model_name_or_path", DEFAULT_BASE_MODEL_ID)
    adapter_digest = sha256_file(adapter_model)

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        import torch
    except ModuleNotFoundError as exc:
        raise StructureOrInputError(
            f"병합에 필요한 패키지 없음: {exc.name}"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    base = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=getattr(torch, "bfloat16"),
        device_map="cpu",
    )
    model = PeftModel.from_pretrained(base, str(adapter_path))
    if not hasattr(model, "merge_and_unload"):
        raise ConversionStageError("merge_and_unload() 미지원 모델")

    merged = model.merge_and_unload()
    output_path.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    merged_files = sorted(output_path.glob("*.safetensors")) + sorted(
        output_path.glob("pytorch_model*.bin")
    )
    if not merged_files:
        raise ConversionStageError("병합 결과 weight 파일이 생성되지 않았습니다")

    merged_digest = sha256_file(merged_files[0])
    print("MERGE_OK=1")
    return {
        "base_model_id": base_model_id,
        "adapter_digest": adapter_digest,
        "merged_digest": merged_digest,
        "merged_model_file": merged_files[0].name,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    try:
        merge(args.adapter_dir, args.output_dir)
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ConversionStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
