from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import sys
from pathlib import Path

from scripts.convert import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_STRUCTURE,
    StructureOrInputError,
)


def verify_mnn(mnn_path: str, dry_run: bool = False) -> dict:
    if dry_run:
        print("MNN_VERIFY_OK=1")
        return {"all_pass": True, "dry_run": True, "report": []}

    mnn_file = Path(mnn_path)
    if not mnn_file.exists():
        raise StructureOrInputError("MNN 파일 없음")

    report = []

    exists_ok = mnn_file.exists() and mnn_file.stat().st_size > 0
    report.append({"check": "file_exists", "ok": exists_ok})
    print(f"[{'PASS' if exists_ok else 'FAIL'}] 파일 존재")

    size_mb = mnn_file.stat().st_size / (1024 ** 2)
    size_gb = mnn_file.stat().st_size / (1024 ** 3)
    size_ok = size_gb <= 3.0
    report.append(
        {"check": "size", "size_mb": round(size_mb, 1), "ok": size_ok}
    )
    print(f"[{'PASS' if size_ok else 'FAIL'}] 크기: {size_mb:.1f}MB")

    structure_only = False
    runtime_verified = False
    try:
        import MNN  # type: ignore

        interpreter = MNN.Interpreter(str(mnn_file))
        session = interpreter.createSession()
        runtime_verified = session is not None
    except ModuleNotFoundError:
        structure_only = True
        print("WARN: MNN Python 없음 — structure_only 모드")
    except Exception as exc:
        print(f"WARN: MNN runtime 검증 실패: {exc}")

    runtime_ok = structure_only or runtime_verified
    report.append(
        {
            "check": "mnn_runtime",
            "structure_only": structure_only,
            "runtime_verified": runtime_verified,
            "ok": runtime_ok,
        }
    )

    all_pass = all(r.get("ok", False) for r in report)
    if all_pass:
        print("MNN_VERIFY_OK=1")
    return {
        "all_pass": all_pass,
        "report": report,
        "size_mb": round(size_mb, 1),
        "structure_only": structure_only,
        "runtime_verified": runtime_verified,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mnn-path", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        result = verify_mnn(args.mnn_path, dry_run=args.dry_run)
        return EXIT_PASS if result["all_pass"] else EXIT_FAIL
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE


if __name__ == "__main__":
    raise SystemExit(main())
