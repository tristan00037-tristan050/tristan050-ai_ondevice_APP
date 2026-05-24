#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil, sys
from pathlib import Path
from typing import List

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src.ip3.telemetry_schema import normalize_platform_name, validate_telemetry_file


def main() -> int:
    ap = argparse.ArgumentParser(description="Import GitHub Actions matrix telemetry artifacts into evidence/.")
    ap.add_argument("root")
    ap.add_argument("artifact_root")
    ap.add_argument("--expected-evidence-class", choices=["ci_lab", "vm_lab", "physical_lab"], default="ci_lab")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    errors: List[str] = []
    copied: List[str] = []
    if not artifact_root.exists():
        print(f"CI_ARTIFACT_IMPORT_FAIL missing artifact_root={artifact_root}", file=sys.stderr)
        return 2
    for platform in ("linux", "darwin", "windows"):
        candidates = sorted(artifact_root.rglob(f"real_telemetry_{platform}.json"))
        if not candidates:
            errors.append(f"missing real_telemetry_{platform}.json in {artifact_root}")
            continue
        src = candidates[0]
        result = validate_telemetry_file(src, expected_platform=platform, expected_evidence_class=args.expected_evidence_class)
        if not result.ok:
            errors.append(f"invalid {src}: {'; '.join(result.errors)}")
            continue
        dst = root / "evidence" / f"real_telemetry_{platform}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(str(dst.relative_to(root)))
    if errors:
        for err in errors:
            print(f"CI_ARTIFACT_IMPORT_FAIL {err}", file=sys.stderr)
        return 2
    print(f"CI_ARTIFACT_IMPORT_OK files={len(copied)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
