from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REQUIRED_DIGEST_KEYS = {"reference_set_digest", "draft_request_digest"}

def load_cases(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

def evaluate_cases(path: str | Path) -> dict[str, Any]:
    cases = load_cases(path)
    raw_key_hits = []
    for case in cases:
        for key in case:
            if key in {"raw_text", "reference_text", "draft_text", "prompt", "absolute_local_path", "filename", "file_name"}:
                raw_key_hits.append({"case_id": case.get("case_id"), "key": key})
        for key in _REQUIRED_DIGEST_KEYS:
            value = case.get(key, "")
            if not (isinstance(value, str) and value.startswith("sha256:") and len(value) == 71):
                raw_key_hits.append({"case_id": case.get("case_id"), "key": key + "_BAD_DIGEST"})
    table_or_figure_count = sum(1 for case in cases if case.get("requires_table_or_figure") is True)
    return {
        "schema_version": "box3.real_follow_up_eval.v1_1",
        "sample_count": len(cases),
        "table_or_figure_count": table_or_figure_count,
        "raw_key_hits": raw_key_hits,
        "verdict_only": True,
        "pass": len(cases) >= 40 and table_or_figure_count >= 8 and not raw_key_hits,
    }

def main() -> None:
    default = Path(__file__).with_name("box3_real_follow_up_cases_v1_1.jsonl")
    print(json.dumps(evaluate_cases(default), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
