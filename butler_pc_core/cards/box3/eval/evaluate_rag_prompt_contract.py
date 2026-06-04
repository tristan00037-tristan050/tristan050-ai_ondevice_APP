from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FORBIDDEN_KEYS = {"reference_text", "draft_text", "prompt", "output", "file_path", "absolute_local_path", "source_doc_name"}


def evaluate_cases(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    raw_key_hits = []
    table_count = 0
    tags = set()
    for idx, row in enumerate(rows, start=1):
        for key in row:
            if key in FORBIDDEN_KEYS or key.startswith("raw_"):
                raw_key_hits.append({"row": idx, "key_digest": "forbidden"})
        if row.get("has_table_or_figure"):
            table_count += 1
        tags.add(row.get("regression_tag"))
    required_tags = {"positive_grounded", "abstain_slot", "injection_defense", "no_name_hallucination", "pr780_blocked_regression"}
    return {
        "schema_version": "box3.rag_prompt_eval.v1_2",
        "sample_count": len(rows),
        "table_or_figure_count": table_count,
        "regression_tags_present": sorted(tag for tag in tags if tag),
        "raw_key_hit_count": len(raw_key_hits),
        "verdict_only": True,
        "pass": len(rows) >= 40 and table_count >= 8 and required_tags.issubset(tags) and not raw_key_hits,
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(evaluate_cases(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("box3_rag_prompt_cases_v1_2.jsonl")), ensure_ascii=False, indent=2, sort_keys=True))
