from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def resolve_mnnconvert_binary() -> str | None:
    return os.getenv("MNNCONVERT_BIN") or shutil.which("MNNConvert")


def convert_to_mnn(onnx_path: str, output_path: str, quantize: bool = True) -> dict:
    onnx_file = Path(onnx_path)
    out_file = Path(output_path)
    binary = resolve_mnnconvert_binary()

    if binary is None:
        raise StructureOrInputError("MNNConvert 바이너리 없음")
    if not onnx_file.exists():
        raise StructureOrInputError("ONNX 파일 없음")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    Path("tmp").mkdir(exist_ok=True)

    quant_bits = 8 if quantize else 0
    cmd = [
        binary,
        "-f",
        "ONNX",
        "--modelFile",
        str(onnx_file),
        "--MNNModel",
        str(out_file),
        "--bizCode",
        "butler",
    ]
    if quantize:
        cmd.extend(["--weightQuantBits", str(quant_bits)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    stdout_path = Path("tmp") / "convert_mnn_stdout.txt"
    stderr_path = Path("tmp") / "convert_mnn_stderr.txt"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    if result.returncode != 0:
        raise ConversionStageError(f"MNN 변환 실패 (exit={result.returncode})")
    if not out_file.exists():
        raise ConversionStageError("MNN 파일 미생성")

    onnx_digest = sha256_file(onnx_file)
    mnn_digest = sha256_file(out_file)
    stdout_digest = sha256_text(result.stdout)
    stderr_digest = sha256_text(result.stderr)
    size_mb = out_file.stat().st_size / (1024 ** 2)
    print("MNN_CONVERT_OK=1")
    return {
        "onnx_digest": onnx_digest,
        "mnn_digest": mnn_digest,
        "quant_bits": quant_bits,
        "size_mb": round(size_mb, 1),
        "command": cmd,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_digest": stdout_digest,
        "stderr_digest": stderr_digest,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx-path", required=True)
    ap.add_argument("--output-path", required=True)
    ap.add_argument("--no-quantize", action="store_true")
    args = ap.parse_args()
    try:
        convert_to_mnn(args.onnx_path, args.output_path, quantize=not args.no_quantize)
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ConversionStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
