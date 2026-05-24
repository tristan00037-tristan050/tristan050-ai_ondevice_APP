#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Dict, List

REQUIRED_CLASSES = ["ci_lab", "vm_lab", "physical_lab", "production"]
REQUIRED_TIERS = ["real_runtime_measurement", "secure_lab", "sample"]


def load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate evidence-class taxonomy and release-claim guardrails.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    path = root / "evidence" / "evidence_class_taxonomy.json"
    errors: List[str] = []
    if not path.exists():
        errors.append("missing evidence/evidence_class_taxonomy.json")
    else:
        doc = load(path)
        classes = doc.get("classes")
        tiers = doc.get("tiers")
        if not isinstance(classes, dict):
            errors.append("classes must be object")
        else:
            for cls in REQUIRED_CLASSES:
                block = classes.get(cls)
                if not isinstance(block, dict):
                    errors.append(f"missing class {cls}")
                    continue
                if cls == "production" and block.get("currently_claimable") is not False:
                    errors.append("production.currently_claimable must be false in v1.3 lab pack")
                if cls in {"ci_lab", "vm_lab"} and block.get("can_claim_physical_windows") is not False:
                    errors.append(f"{cls}.can_claim_physical_windows must be false")
                if cls != "production" and block.get("can_claim_production") is not False:
                    errors.append(f"{cls}.can_claim_production must be false")
        if not isinstance(tiers, dict):
            errors.append("tiers must be object")
        else:
            for tier in REQUIRED_TIERS:
                if tier not in tiers:
                    errors.append(f"missing tier {tier}")
    if errors:
        for err in errors:
            print(f"EVIDENCE_TAXONOMY_GATE_FAIL {err}", file=sys.stderr)
        return 2
    print("EVIDENCE_TAXONOMY_GATE_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
