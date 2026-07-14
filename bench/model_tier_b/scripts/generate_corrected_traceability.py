#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "v2.8" / "02_구현계약" / "defect_traceability_46_v2.8.csv"
OUTPUT = ROOT / "evidence" / "local_validation" / "defect_traceability_46_v2.8.corrected.csv"

AREA = {
    "SRC": ([f"AC-SRC-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(25, 30)]),
    "POL": ([f"AC-POL-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(30, 35)]),
    "BOX": ([f"AC-BOX-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(36, 41)]),
    "WRK": ([f"AC-WRK-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(15, 21)]),
    "MOD": ([f"AC-MOD-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(21, 25)]),
    "MEM": ([f"AC-MEM-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(53, 57)]),
    "DUAL": ([f"AC-DUAL-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(12, 15)]),
    "EGR": ([f"AC-EGR-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(7, 12)]),
    "EVD": ([f"AC-EVD-{i:02d}" for i in range(1, 7)], ["ATK-001", *[f"ATK-{i:03d}" for i in range(45, 49)]]),
    "VER": ([f"AC-VER-{i:02d}" for i in range(1, 7)], ["ATK-041", "ATK-042"]),
    "SCN": ([f"AC-SCN-{i:02d}" for i in range(1, 7)], [*[f"ATK-{i:03d}" for i in range(2, 7)], "ATK-058", "ATK-059"]),
    "SCH": ([f"AC-SCH-{i:02d}" for i in range(1, 7)], [f"ATK-{i:03d}" for i in range(49, 53)]),
    "CI": ([f"AC-CI-{i:02d}" for i in range(1, 7)], ["ATK-035", "ATK-060"]),
    "GOV": ([f"AC-GOV-{i:02d}" for i in range(1, 7)], ["ATK-043", "ATK-044"]),
    "ENG": ([f"AC-ENG-{i:02d}" for i in range(1, 7)], ["ATK-057"]),
}

MAPPING = {
    "V26-P0-001": ["VER", "EVD"], "V26-P0-002": ["SCN"], "V26-P0-003": ["EGR"], "V26-P0-004": ["DUAL"],
    "V26-P0-005": ["WRK"], "V26-P0-006": ["BOX", "SCH"], "V26-P0-007": ["BOX"], "V26-P0-008": ["VER"],
    "V26-P0-009": ["MOD", "WRK"], "V26-P0-010": ["POL"], "V26-P0-011": ["BOX", "CI"], "V26-P0-012": ["CI", "GOV"],
    "V26-P1-013": ["WRK"], "V26-P1-014": ["MOD"], "V26-P1-015": ["MEM", "WRK"], "V26-P1-016": ["SRC", "CI"],
    "ALG-P0-001": ["EVD"], "ALG-P0-002": ["SCN"], "ALG-P0-003": ["GOV"], "ALG-P0-004": ["BOX"],
    "ALG-P0-005": ["GOV"], "ALG-P0-006": ["EGR"], "ALG-P0-007": ["VER"], "ALG-P0-008": ["VER"],
    "ALG-P0-009": ["EVD", "VER"], "ALG-P0-010": ["BOX", "CI"], "ALG-P0-011": ["POL", "CI", "GOV"],
    "ALG-P1-012": ["WRK"], "ALG-P1-013": ["SCN", "CI"], "ALG-P1-014": ["SRC"], "ALG-P1-015": ["POL", "CI"], "ALG-P1-016": ["MOD"],
    "COD-P0-001": ["BOX", "GOV"], "COD-P0-002": ["EGR", "CI", "GOV"], "COD-P1-003": ["VER", "EVD"],
    "COD-P1-004": ["POL"], "COD-P1-005": ["WRK"], "COD-P1-006": ["SRC", "CI"], "COD-P1-007": ["SRC"],
    "COM-P0-001": ["GOV"], "COM-P0-002": ["DUAL", "MOD"], "COM-P0-003": ["POL", "CI"], "COM-P1-004": ["WRK"],
    "COM-P1-005": ["ENG"], "COM-P1-006": ["MEM"], "COM-P1-007": ["SCH"],
}

REQUIREMENT = {
    "SRC": "full Git OID/tree, submodule/LFS, blob and deployment digest separation",
    "POL": "canonical approved policy and signed trust claims",
    "BOX": "real product entrypoints, one repair, authoritative terminal gate",
    "WRK": "bounded parent-observed worker FSM and process provenance",
    "MOD": "closed model tree, tokenizer/config, pre/post descriptor digest",
    "MEM": "sampler identity, eight marks, PID scope, Metal/thermal/power",
    "DUAL": "distinct physical models, PIDs, overlap and bilateral inference",
    "EGR": "approved OS controller, full interval and native/subprocess probes",
    "EVD": "mandatory receipt cardinality and orphan/cycle-free final DAG",
    "VER": "verified evaluator artifact and producer-independent offline replay",
    "SCN": "registered binary and recursive multi-encoding archive scan",
    "SCH": "5 epochs, representative warmup, AB/BA and no cherry-picking",
    "CI": "12-job digest-linked CI and signed attestation replay",
    "GOV": "11 signed gate receipts, no caller boolean and no premature G1",
    "ENG": "verified meter or explicit NOT_MEASURED/NO_DECISION",
}


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result: result.append(value)
    return result


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream: rows = list(csv.DictReader(stream))
    if set(MAPPING) != {row["defect_id"] for row in rows}: raise SystemExit("explicit defect mapping is incomplete")
    output = []
    for row in rows:
        areas = MAPPING[row["defect_id"]]
        acceptance = unique([item for area in areas for item in AREA[area][0]])
        attacks = unique([item for area in areas for item in AREA[area][1]])
        output.append({**row, "v2_8_requirement": " + ".join(REQUIREMENT[area] for area in areas), "acceptance_ids": ";".join(acceptance), "attack_ids": ";".join(attacks), "current_status": "LOCAL_CODE_TESTED_EXTERNAL_EVIDENCE_REQUIRED", "mapping_correction_reason": "원본 영역 오매핑 교정; 제목·실패경로 기준 explicit remap"})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)


if __name__ == "__main__": main()
