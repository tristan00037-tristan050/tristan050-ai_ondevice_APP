from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import hashlib
import inspect
import sys
from pathlib import Path
from typing import Any, Callable

from scripts.convert import EXIT_PASS, EXIT_STRUCTURE, StructureOrInputError


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_ort_converter():
    try:
        from onnxruntime.tools import convert_onnx_models_to_ort
    except ModuleNotFoundError:
        return None
    return convert_onnx_models_to_ort


def _resolve_convert_function(module_or_callable) -> Callable[..., Any] | None:
    if module_or_callable is None:
        return None
    if callable(module_or_callable):
        return module_or_callable
    fn = getattr(module_or_callable, "convert_onnx_models_to_ort", None)
    if callable(fn):
        return fn
    return None


def _invoke_converter(converter_fn: Callable[..., Any], onnx_dir: Path, output_dir: Path, optimization_style: str) -> None:
    sig = inspect.signature(converter_fn)
    kwargs: dict[str, Any] = {}
    params = sig.parameters
    if "output_dir" in params:
        kwargs["output_dir"] = str(output_dir)
    if "optimization_style" in params:
        kwargs["optimization_style"] = optimization_style
    if "enable_type_reduction" in params:
        kwargs["enable_type_reduction"] = True
    if "save_optimized_onnx_model" in params:
        kwargs["save_optimized_onnx_model"] = False
    if "allow_conversion_failures" in params:
        kwargs["allow_conversion_failures"] = False

    positional = []
    if params:
        positional.append(str(onnx_dir))
    converter_fn(*positional, **kwargs)


def convert_to_ort(onnx_path: str, output_path: str, optimization_style: str = "Fixed") -> dict:
    onnx_file = Path(onnx_path)
    out_file = Path(output_path)
    if not onnx_file.exists():
        raise StructureOrInputError("ONNX 파일 없음")

    converter_module = _load_ort_converter()
    converter_fn = _resolve_convert_function(converter_module)
    if converter_fn is None:
        print("WARN: onnxruntime-tools/onnxruntime.tools 없음 — ORT mobile 변환 건너뜀")
        return {"skipped": True, "reason": "onnxruntime-tools not installed"}

    out_file.parent.mkdir(parents=True, exist_ok=True)
    print("ORT mobile format 변환 중...")
    _invoke_converter(converter_fn, onnx_file.parent, out_file.parent, optimization_style)

    if not out_file.exists():
        # 변환기가 stem 기반 파일명을 쓸 경우 fallback
        candidates = sorted(out_file.parent.glob("*.ort"))
        if not candidates:
            print("WARN: ORT 파일 미생성 — 환경 미지원 가능성")
            return {"skipped": True, "reason": "no ort files generated"}
        out_file = candidates[0]

    ort_file = out_file
    size_mb = ort_file.stat().st_size / (1024 ** 2)
    ort_digest = _sha256_file(ort_file)
    print("ORT_CONVERT_OK=1")
    print(f"ORT 파일 크기: {size_mb:.1f}MB")
    return {
        "ort_path": str(ort_file),
        "size_mb": round(size_mb, 1),
        "ort_digest": ort_digest,
        "optimization_style": optimization_style,
        "skipped": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx-path", required=True)
    ap.add_argument("--output-path", required=True)
    args = ap.parse_args()
    try:
        convert_to_ort(args.onnx_path, args.output_path)
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE


if __name__ == "__main__":
    raise SystemExit(main())
