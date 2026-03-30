from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from scripts.convert import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_STRUCTURE,
    ConversionStageError,
    StructureOrInputError,
)


def _budget_to_dict(result):
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if is_dataclass(result):
        return asdict(result)
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    return {"value": result}


def run_pipeline(
    adapter_dir: str,
    work_dir: str,
    package_dir: str,
    version: str,
    dry_run: bool = False,
) -> int:
    start = time.time()
    work = Path(work_dir)
    merged_dir = str(work / "merged")
    onnx_path = str(work / "butler_model.onnx")
    mnn_path = str(work / "butler_model.mnn")
    ort_path = str(work / "ort_mobile" / "butler_model.ort")
    stage_results: dict = {}

    print("=" * 60)
    print("  버틀러 ONNX/MNN 변환 파이프라인")
    print(f"  버전: {version}, dry_run: {dry_run}")
    print("=" * 60)

    from scripts.convert.convert_budget_v1 import check_budget, get_budget_spec
    from scripts.convert.convert_manifest_v1 import create_manifest
    from scripts.convert.convert_verify_mnn_v2 import verify_mnn
    from scripts.convert.convert_verify_onnx_v2 import verify_onnx

    if dry_run:
        verify_onnx("", dry_run=True)
        verify_mnn("", dry_run=True)
        budget_result = check_budget("", dry_run=True)
        stage_results["budget"] = {
            "budget_spec": get_budget_spec(),
            "result": _budget_to_dict(budget_result),
        }
        elapsed = round(time.time() - start, 1)
        create_manifest(
            "dry_run",
            adapter_dir,
            work_dir,
            package_dir,
            version,
            stage_results,
            elapsed,
            config={"opset": 17, "quant_bits": 8, "ort_mobile_enabled": True},
        )
        print("CONVERT_DRYRUN_OK=1")
        return EXIT_PASS

    try:
        from scripts.convert.convert_merge_v1 import merge
        from scripts.convert.convert_mnn_v2 import convert_to_mnn
        from scripts.convert.convert_onnx_v2 import convert_to_onnx
        from scripts.convert.convert_ort_mobile_v1 import convert_to_ort
        from scripts.convert.convert_package_v2 import create_package

        print("[1/8] 어댑터 병합...")
        stage_results["merge"] = merge(adapter_dir, merged_dir)

        print("[2/8] ONNX 변환...")
        stage_results["onnx"] = convert_to_onnx(merged_dir, onnx_path)

        print("[3/8] ONNX 검증...")
        verify_onnx_result = verify_onnx(onnx_path)
        stage_results["verify_onnx"] = verify_onnx_result
        if not verify_onnx_result["all_pass"]:
            raise ConversionStageError("ONNX 검증 실패")

        print("[4/8] ORT mobile 변환...")
        try:
            stage_results["ort_mobile"] = convert_to_ort(onnx_path, ort_path)
        except Exception as exc:  # optional path
            stage_results["ort_mobile"] = {"skipped": True, "reason": str(exc)}
            print(f"WARN: ORT mobile 변환 건너뜀: {exc}")

        print("[5/8] MNN 변환...")
        stage_results["mnn"] = convert_to_mnn(onnx_path, mnn_path)

        print("[6/8] MNN 검증...")
        verify_mnn_result = verify_mnn(mnn_path)
        stage_results["verify_mnn"] = verify_mnn_result
        if not verify_mnn_result["all_pass"]:
            raise ConversionStageError("MNN 검증 실패")

        print("[7/8] 패키지 생성...")
        stage_results["package"] = create_package(
            mnn_path,
            merged_dir,
            package_dir,
            version,
            onnx_digest=stage_results["onnx"].get("onnx_digest"),
            merged_digest=stage_results["merge"].get("merged_digest"),
            external_data_used=stage_results["onnx"].get("external_data_used", False),
            base_model_id=stage_results["merge"].get("base_model_id", "Qwen/Qwen3-4B"),
        )

        print("[8/8] budget + 매니페스트 저장...")
        effective_ort_path = None
        if not stage_results.get("ort_mobile", {}).get("skipped"):
            effective_ort_path = stage_results["ort_mobile"].get("ort_path")
        budget_result = check_budget(mnn_path, effective_ort_path, dry_run=False)
        stage_results["budget"] = {
            "budget_spec": get_budget_spec(),
            "result": _budget_to_dict(budget_result),
        }

        elapsed = round(time.time() - start, 1)
        create_manifest(
            "real_run",
            adapter_dir,
            work_dir,
            package_dir,
            version,
            stage_results,
            elapsed,
            config={
                "opset": stage_results["onnx"].get("opset", 17),
                "quant_bits": stage_results["mnn"].get("quant_bits", 8),
                "ort_mobile_enabled": True,
            },
        )
        print("CONVERT_PIPELINE_OK=1")
        return EXIT_PASS
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ModuleNotFoundError as exc:
        print(f"ERROR: 필수 패키지 없음: {exc.name}", file=sys.stderr)
        return EXIT_STRUCTURE
    except ConversionStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return run_pipeline(
        args.adapter_dir,
        args.work_dir,
        args.package_dir,
        args.version,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
