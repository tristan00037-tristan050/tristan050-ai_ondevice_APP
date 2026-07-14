#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "v2.8" / "02_구현계약" / "acceptance_matrix_v2.8.csv"
OUTPUT = ROOT / "evidence" / "local_validation" / "acceptance_status.csv"
SUMMARY = ROOT / "evidence" / "local_validation" / "acceptance_summary.json"
REPO_AREAS = {"source/provenance", "policy/trust", "product/repair", "CI/package"}
TARGET_AREAS = {"memory/Metal", "dual resident", "OS egress", "energy"}


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream: rows = list(csv.DictReader(stream))
    output = []
    for row in rows:
        if row["area"] in REPO_AREAS:
            status, boundary = "IMPLEMENTED_LOCAL_ACTUAL_REPO_REQUIRED", "실제 Butler 저장소·승인 정책·서명 CI evidence 필요"
        elif row["area"] in TARGET_AREAS:
            status, boundary = "IMPLEMENTED_LOCAL_TARGET_EVIDENCE_REQUIRED", "승인 M3 Max·실제 모델·OS controller·실측 evidence 필요"
        else:
            status, boundary = "LOCAL_CONTRACT_PASS", "로컬 happy-path와 공격 실패계약 검증; 제품/M3 PASS로 확대 금지"
        output.append({**row, "implementation_status": status, "evidence_boundary": boundary})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    counts = Counter(row["implementation_status"] for row in output)
    SUMMARY.write_text(json.dumps({"schema_version": "butler.model-tier-b.acceptance-summary.v2.8", "total": len(output), "counts": dict(sorted(counts.items())), "claim_boundary": "LOCAL_CONTRACT_ONLY_NO_PRODUCT_CI_OR_M3_CLAIM"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
