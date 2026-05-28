#!/usr/bin/env python3
"""Redact raw model output / source / prompt payloads in tracked evidence JSON.

SSOT_V1.md (§4-1, §5-2) scopes the raw-zero rule to 증빙(evidence): only
meta-only values (numbers/status/ID/version) may persist in tracked artifacts.
Codex P2 flagged evidence/box3_eval/*.json for storing full model generations
and source documents as long raw strings.

This replaces each raw-carrying field K (>100 chars) with:
  - {K}_sha256       : full 64-char sha256 of the raw value
  - {K}_length_chars : original char length
keeping the raw text itself out of the tracked tree. Aggregate metrics,
classifications, and analyst findings (separate keys) are left intact.

Idempotent: a field already redacted (no raw key present) is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Keys that carry raw model output, source documents, or prompts.
# Analyst-authored meta fields (recommendation/diagnosis/verdict/rationale/
# qualitative_findings/evaluation_method/limitations) are NOT raw and are kept.
# Keys carrying raw model output / source document content / prompts. Mirrors
# the verify_no_raw_output_v1.sh guard keys (prompt/output/raw_input/raw_response)
# and META_ONLY_BANNED_KEYS (text/content/raw_text), plus the eval `input` doc.
# NOTE: provenance keys like `source`/`reference` (e.g. "PR #741 / path.py") are
# meta references the SSOT allows, so they are intentionally NOT redacted.
RAW_FIELDS = ("output", "input", "prompt", "raw_input", "raw_response", "generated_text", "text", "content", "raw_text")
# 50 chars matches the project excerpt limit (an excerpt >=50 chars counts as
# raw again), and is stricter than the 100-byte report guard, so short Korean
# source fragments (~90 chars = ~270 bytes) are also redacted.
REDACT_THRESHOLD_CHARS = 50


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_obj(obj):
    if isinstance(obj, dict):
        new = {}
        for key, value in obj.items():
            if key in RAW_FIELDS and isinstance(value, str) and len(value) >= REDACT_THRESHOLD_CHARS:
                new[f"{key}_sha256"] = sha256_hex(value)
                new[f"{key}_length_chars"] = len(value)
            else:
                new[key] = redact_obj(value)
        return new
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj


def main(paths: list[str]) -> int:
    for path in paths:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        redacted = redact_obj(data)
        p.write_text(json.dumps(redacted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"redacted: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
