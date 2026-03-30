from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.convert import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_STRUCTURE,
    ConversionStageError,
    StructureOrInputError,
)

REQUIRED_TOKENIZER_FILES = ["tokenizer.json", "tokenizer_config.json"]
OPTIONAL_TOKENIZER_FILES = ["special_tokens_map.json", "vocab.json", "merges.txt"]
OPTIONAL_CONFIG_FILES = ["generation_config.json", "config.json"]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(file.relative_to(path)).encode("utf-8"))
        with file.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()[:16]


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copy2(str(src), str(dst))


def _digest_map(paths: list[Path]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in paths:
        if path.exists() and path.is_file():
            digests[path.name] = sha256_file(path)
    return digests


def create_package(
    mnn_path: str,
    model_dir: str,
    output_dir: str,
    version: str,
    *,
    onnx_digest: str | None = None,
    merged_digest: str | None = None,
    external_data_used: bool = False,
    base_model_id: str = "Qwen/Qwen3-4B",
) -> dict:
    mnn_file = Path(mnn_path)
    model_path = Path(model_dir)
    out_path = Path(output_dir)

    if not mnn_file.exists():
        raise StructureOrInputError(f"MNN 파일 없음: {mnn_path}")
    if onnx_digest is None or merged_digest is None:
        raise StructureOrInputError("placeholder digest 금지 — onnx_digest/merged_digest 필수")

    for filename in REQUIRED_TOKENIZER_FILES:
        if not (model_path / filename).exists():
            raise StructureOrInputError(f"필수 tokenizer 파일 없음: {filename}")

    out_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(mnn_file), str(out_path / "butler_model.mnn"))

    copy_names = REQUIRED_TOKENIZER_FILES + OPTIONAL_TOKENIZER_FILES + OPTIONAL_CONFIG_FILES
    for filename in copy_names:
        _copy_if_exists(model_path / filename, out_path / filename)

    packaged_mnn = out_path / "butler_model.mnn"
    if not packaged_mnn.exists():
        raise ConversionStageError("패키지 복사 실패: butler_model.mnn 없음")

    tokenizer_digests = _digest_map([out_path / name for name in REQUIRED_TOKENIZER_FILES + OPTIONAL_TOKENIZER_FILES])
    config_digests = _digest_map([out_path / name for name in OPTIONAL_CONFIG_FILES])

    mnn_digest = sha256_file(packaged_mnn)
    pkg_digest = sha256_dir(out_path)
    size_mb = packaged_mnn.stat().st_size / (1024 ** 2)
    manifest = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_model_id": base_model_id,
        "merged_model_digest": merged_digest,
        "onnx_digest": onnx_digest,
        "mnn_digest": mnn_digest,
        "size_mb": round(size_mb, 1),
        "quantization": "int8",
        "target_platforms": ["iOS", "Android", "macOS"],
        "external_data_used": external_data_used,
        "tokenizer_file_digests": tokenizer_digests,
        "config_file_digests": config_digests,
        "generation_config_digest": config_digests.get("generation_config.json"),
        "packaged_file_digests": {**tokenizer_digests, **config_digests, "butler_model.mnn": mnn_digest},
    }
    (out_path / "package_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("PACKAGE_OK=1")
    return {
        "pkg_digest": pkg_digest,
        "manifest": manifest,
        "tokenizer_digests": tokenizer_digests,
        "config_digests": config_digests,
        "generation_config_digest": config_digests.get("generation_config.json"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mnn-path", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--onnx-digest")
    ap.add_argument("--merged-digest")
    args = ap.parse_args()
    try:
        create_package(
            args.mnn_path,
            args.model_dir,
            args.output_dir,
            args.version,
            onnx_digest=args.onnx_digest,
            merged_digest=args.merged_digest,
        )
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ConversionStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
