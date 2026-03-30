from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import hashlib
import inspect
import traceback
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


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _torch_no_grad(torch_mod):
    return getattr(torch_mod, "no_grad")()


def _build_dynamic_shapes() -> Dict[str, Dict[int, str]]:
    return {
        "input_ids": {0: "batch", 1: "sequence_length"},
        "attention_mask": {0: "batch", 1: "sequence_length"},
    }


def _prepare_legacy_axes() -> Dict[str, Dict[int, str]]:
    return {
        "input_ids": {0: "batch", 1: "sequence_length"},
        "attention_mask": {0: "batch", 1: "sequence_length"},
        "logits": {0: "batch", 1: "sequence_length"},
    }


def _export_dynamo(torch_mod, model, input_ids, attention_mask, out_path: Path, opset: int) -> None:
    export_sig = inspect.signature(torch_mod.onnx.export)
    kwargs: Dict[str, Any] = {
        "opset_version": opset,
        "input_names": ["input_ids", "attention_mask"],
        "output_names": ["logits"],
        "do_constant_folding": True,
    }
    if "dynamo" in export_sig.parameters:
        kwargs["dynamo"] = True
    if "external_data" in export_sig.parameters:
        kwargs["external_data"] = True
    if "dynamic_shapes" in export_sig.parameters:
        kwargs["dynamic_shapes"] = _build_dynamic_shapes()
    elif "dynamic_axes" in export_sig.parameters:
        kwargs["dynamic_axes"] = _prepare_legacy_axes()
    if "report" in export_sig.parameters:
        kwargs["report"] = True
    if "artifacts_dir" in export_sig.parameters:
        kwargs["artifacts_dir"] = str(Path("tmp"))

    with _torch_no_grad(torch_mod):
        torch_mod.onnx.export(
            model,
            (input_ids, attention_mask),
            str(out_path),
            **kwargs,
        )


def _export_legacy(torch_mod, model, input_ids, attention_mask, out_path: Path, opset: int) -> None:
    with _torch_no_grad(torch_mod):
        torch_mod.onnx.export(
            model,
            (input_ids, attention_mask),
            str(out_path),
            opset_version=opset,
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes=_prepare_legacy_axes(),
            do_constant_folding=True,
        )


def _guess_external_data_files(out_path: Path) -> list[Path]:
    candidates = [
        out_path.with_suffix(out_path.suffix + ".data"),
        out_path.parent / f"{out_path.name}.data",
    ]
    discovered = [p for p in candidates if p.exists()]
    if discovered:
        return discovered
    return sorted(out_path.parent.glob("*.data")) + sorted(out_path.parent.glob("*.onnx.data"))


def convert_to_onnx(model_dir: str, output_path: str, opset: int = 17) -> dict:
    model_path = Path(model_dir)
    out_path = Path(output_path)
    if not model_path.exists():
        raise StructureOrInputError(f"모델 디렉터리 없음: {model_path}")

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ModuleNotFoundError as exc:
        raise StructureOrInputError(
            f"ONNX 변환에 필요한 패키지 없음: {exc.name}"
        ) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Path("tmp").mkdir(exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(str(model_path))
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        torch_dtype=getattr(torch, "float16"),
        device_map="cpu",
    )
    if hasattr(model, "eval"):
        model.eval()

    dummy = tokenizer("버틀러 테스트", return_tensors="pt")
    input_ids = dummy["input_ids"]
    attention_mask = dummy.get("attention_mask")
    if attention_mask is None:
        attention_mask = input_ids

    export_method = ""
    try:
        _export_dynamo(torch, model, input_ids, attention_mask, out_path, opset)
        export_method = "torch.onnx.export:dynamo"
    except Exception as exc:
        (Path("tmp") / "onnx_export_debug.txt").write_text(
            "".join(traceback.format_exception(exc)),
            encoding="utf-8",
        )
        try:
            _export_legacy(torch, model, input_ids, attention_mask, out_path, opset)
            export_method = "torch.onnx.export:legacy"
        except Exception as fallback_exc:
            (Path("tmp") / "onnx_export_fallback_debug.txt").write_text(
                "".join(traceback.format_exception(fallback_exc)),
                encoding="utf-8",
            )
            raise ConversionStageError(f"ONNX export 완전 실패: {fallback_exc}") from fallback_exc

    if not out_path.exists():
        raise ConversionStageError("ONNX 파일이 생성되지 않았습니다")

    data_files = _guess_external_data_files(out_path)
    external_data_used = bool(data_files)
    size_mb = out_path.stat().st_size / (1024 ** 2)
    onnx_digest = sha256_file(out_path)

    print("ONNX_CONVERT_OK=1")
    return {
        "export_method": export_method,
        "opset": int(opset),
        "size_mb": round(size_mb, 1),
        "onnx_digest": onnx_digest,
        "external_data_used": external_data_used,
        "output_path": str(out_path),
        "external_data_files": [p.name for p in data_files],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--output-path", required=True)
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()
    try:
        convert_to_onnx(args.model_dir, args.output_path, args.opset)
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ConversionStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
