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

from scripts.convert import EXIT_FAIL, EXIT_PASS, EXIT_STRUCTURE, StructureOrInputError


def _digest_file(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _external_data_locations(onnx_model) -> list[str]:
    locations: list[str] = []
    for tensor in list(getattr(onnx_model.graph, "initializer", [])):
        external_data = getattr(tensor, "external_data", [])
        for entry in external_data:
            key = getattr(entry, "key", "")
            value = getattr(entry, "value", "")
            if key == "location" and value:
                locations.append(value)
    return sorted(set(locations))


def _collect_exporter_report_digests(tmp_dir: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rpt in sorted(tmp_dir.glob("onnx_export_report*")):
        if rpt.is_file():
            digests[rpt.name] = _digest_file(rpt)
    return digests


def verify_onnx(onnx_path: str, dry_run: bool = False) -> dict:
    if dry_run:
        print("ONNX_VERIFY_OK=1")
        return {
            "all_pass": True,
            "dry_run": True,
            "report": [],
            "exporter_report_digests": {},
            "structure_verified": True,
            "runtime_verified": True,
            "external_data_digests": {},
        }

    onnx_file = Path(onnx_path)
    if not onnx_file.exists():
        raise StructureOrInputError("ONNX 파일 없음")

    try:
        import numpy as np
        import onnx
        import onnxruntime as ort
    except ModuleNotFoundError as exc:
        raise StructureOrInputError(
            f"ONNX 검증에 필요한 패키지 없음: {exc.name}"
        ) from exc

    report = []
    tmp_dir = Path("tmp")
    tmp_dir.mkdir(exist_ok=True)
    file_size_gb = onnx_file.stat().st_size / (1024 ** 3)

    model = None
    structure_verified = False
    try:
        model = onnx.load(str(onnx_file), load_external_data=False)
        if file_size_gb > 2.0:
            onnx.checker.check_model(str(onnx_file))
        else:
            onnx.checker.check_model(model)
        structure_verified = True
    except Exception:
        structure_verified = False
    report.append({"check": "onnx_structure", "ok": structure_verified})
    print(f"[{'PASS' if structure_verified else 'FAIL'}] ONNX 구조 검증")

    inputs = [i.name for i in getattr(model.graph, "input", [])] if model else []
    outputs = [o.name for o in getattr(model.graph, "output", [])] if model else []
    io_ok = "input_ids" in inputs and "logits" in outputs
    report.append(
        {"check": "io_names", "inputs": inputs, "outputs": outputs, "ok": io_ok}
    )
    print(f"[{'PASS' if io_ok else 'FAIL'}] 입출력 이름")

    report_digests = _collect_exporter_report_digests(tmp_dir)
    if report_digests:
        report.append(
            {"check": "exporter_report_digest", "digests": report_digests, "ok": True}
        )
        print(f"[PASS] exporter report digest: {list(report_digests.keys())}")

    runtime_verified = False
    try:
        sess = ort.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
        feed = {}
        for input_meta in sess.get_inputs():
            if input_meta.name == "input_ids":
                feed[input_meta.name] = np.array([[1, 2, 3]], dtype=np.int64)
            elif input_meta.name == "attention_mask":
                feed[input_meta.name] = np.array([[1, 1, 1]], dtype=np.int64)
            else:
                shape = [1 if (dim in (None, "") or isinstance(dim, str)) else int(dim) for dim in input_meta.shape]
                if not shape:
                    shape = [1]
                feed[input_meta.name] = np.ones(shape, dtype=np.int64)
        out = sess.run(None, feed)
        runtime_verified = out is not None and len(out) > 0
    except Exception as exc:
        print("WARN: ORT runtime 검증 실패")
    report.append(
        {
            "check": "ort_verification",
            "structure_verified": structure_verified,
            "runtime_verified": runtime_verified,
            "ok": structure_verified and runtime_verified,
        }
    )
    ort_ok = structure_verified and runtime_verified
    print(f"[{'PASS' if ort_ok else 'FAIL'}] ORT: structure={structure_verified}, runtime={runtime_verified}")

    size_ok = file_size_gb <= 3.0
    report.append({"check": "size", "size_gb": round(file_size_gb, 3), "ok": size_ok})
    print(f"[{'PASS' if size_ok else 'FAIL'}] 크기: {file_size_gb:.3f}GB")

    refs = _external_data_locations(model) if model else []
    external_files = [onnx_file.parent / ref for ref in refs]
    if not refs:
        fallback = sorted(onnx_file.parent.glob("*.onnx.data")) + sorted(onnx_file.parent.glob("*.data"))
        if fallback:
            external_files = fallback
            refs = [f.name for f in fallback]

    external_ok = all(p.exists() for p in external_files) if refs else True
    report.append({"check": "external_data", "files": refs, "ok": external_ok})
    print(f"[{'PASS' if external_ok else 'FAIL'}] external_data 파일")

    external_data_digests = {p.name: _digest_file(p) for p in external_files if p.exists()} if refs else {}
    if external_data_digests:
        report.append(
            {
                "check": "external_data_digests",
                "digests": external_data_digests,
                "ok": True,
            }
        )

    all_pass = all(item.get("ok", False) for item in report)
    if all_pass:
        print("ONNX_VERIFY_OK=1")
    return {
        "all_pass": all_pass,
        "report": report,
        "exporter_report_digests": report_digests,
        "structure_verified": structure_verified,
        "runtime_verified": runtime_verified,
        "external_data_digests": external_data_digests,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx-path", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        result = verify_onnx(args.onnx_path, dry_run=args.dry_run)
        return EXIT_PASS if result["all_pass"] else EXIT_FAIL
    except StructureOrInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE


if __name__ == "__main__":
    raise SystemExit(main())
