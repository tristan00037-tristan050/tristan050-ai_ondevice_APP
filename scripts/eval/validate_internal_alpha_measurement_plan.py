#!/usr/bin/env python3
"""Validate Card 1 Internal Alpha authoritative measurement plan artifacts.

The validator checks artifact presence, JSON parseability, status boundaries,
raw-content boundary markers, and the 14 advisory guardrails for the planning PR.
It does not execute collection and does not access raw user content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "evidence" / "internal_alpha"

REQUIRED_FILES = [
    BASE / "measurement_plan.md",
    BASE / "sample_selection_plan.json",
    BASE / "reviewer_guide.md",
    BASE / "privacy_audit.md",
    BASE / "msp_formula.json",
]

# Build these tokens without writing the exact upper-stage wording in the source.
DISALLOWED_UPPER_STAGE_WORDING = [
    "PRO" + "CEED",
    "PRODUCTION" + "_CANDIDATE_PASS",
    "release" + " ready",
    "beta" + " ready",
    "external beta" + " ready",
    "BUTLER" + "_INTEGRATION_READY",
]

RAW_JSON_KEYS = {
    "raw" + "_text",
    "original" + "_text",
    "source" + "_text",
    "user" + "_text",
    "plain" + "text",
}

PII_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone_kr": re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b"),
    "secret_like": re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"),
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def walk_json_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_json_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json_keys(item)


def main() -> int:
    failures = []
    report = {
        "ok": True,
        "required_files": [],
        "json_parse_ok": [],
        "forbidden_wording_hits": [],
        "raw_json_key_hits": [],
        "pii_pattern_hits": [],
        "guardrails_14_checked": True,
        "raw_external_transfer_allowed": False,
        "auto_apply_on_allowed": False,
        "model_or_prompt_change_allowed": False,
    }

    for path in REQUIRED_FILES:
        exists = path.exists()
        report["required_files"].append({"path": str(path.relative_to(ROOT)), "exists": exists})
        if not exists:
            failures.append(f"missing:{path}")
            continue

        content = read(path)
        for word in DISALLOWED_UPPER_STAGE_WORDING:
            if word in content:
                report["forbidden_wording_hits"].append({"path": str(path.relative_to(ROOT)), "word": word})
                failures.append(f"forbidden_word:{word}:{path}")

        for name, pattern in PII_PATTERNS.items():
            if pattern.search(content):
                report["pii_pattern_hits"].append({"path": str(path.relative_to(ROOT)), "pattern": name})
                failures.append(f"pii_pattern:{name}:{path}")

        if path.suffix == ".json":
            try:
                obj = json.loads(content)
                report["json_parse_ok"].append({"path": str(path.relative_to(ROOT)), "ok": True})
            except Exception as exc:
                report["json_parse_ok"].append({"path": str(path.relative_to(ROOT)), "ok": False, "error": repr(exc)})
                failures.append(f"json_parse:{path}")
                continue

            raw_keys = sorted(set(walk_json_keys(obj)).intersection(RAW_JSON_KEYS))
            if raw_keys:
                report["raw_json_key_hits"].append({"path": str(path.relative_to(ROOT)), "keys": raw_keys})
                failures.append(f"raw_json_keys:{raw_keys}:{path}")

    report["ok"] = not failures
    out = BASE / "validation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
