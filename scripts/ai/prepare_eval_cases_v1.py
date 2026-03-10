#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

EVAL_CASES = [
    ("qa", "placeholder_qa_01"), ("qa", "placeholder_qa_02"),
    ("qa", "placeholder_qa_03"), ("qa", "placeholder_qa_04"),
    ("qa", "placeholder_qa_05"), ("qa", "placeholder_qa_06"),
    ("summarize", "placeholder_summarize_01"), ("summarize", "placeholder_summarize_02"),
    ("summarize", "placeholder_summarize_03"), ("summarize", "placeholder_summarize_04"),
    ("rewrite", "placeholder_rewrite_01"), ("rewrite", "placeholder_rewrite_02"),
    ("rewrite", "placeholder_rewrite_03"), ("rewrite", "placeholder_rewrite_04"),
    ("tool_call", "placeholder_tool_01"), ("tool_call", "placeholder_tool_02"),
    ("tool_call", "placeholder_tool_03"), ("tool_call", "placeholder_tool_04"),
    ("policy_sensitive", "placeholder_policy_01"), ("policy_sensitive", "placeholder_policy_02"),
    ("policy_sensitive", "placeholder_policy_03"),
    ("retrieval_transform", "placeholder_retrieval_01"),
    ("retrieval_transform", "placeholder_retrieval_02"),
    ("retrieval_transform", "placeholder_retrieval_03"),
]

def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def main() -> None:
    out = [
        {"case_id": f"case_{idx:02d}", "prompt_class_id": cls, "input_digest_sha256": digest_text(raw)}
        for idx, (cls, raw) in enumerate(EVAL_CASES, start=1)
    ]
    path = Path("tmp/eval_cases_v1.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EVAL_CASES_PREPARED=1")

if __name__ == "__main__":
    main()
