from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json, re, zipfile

from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl


def generate_rows(input_dir: str):
    rows = []
    for zip_fp in sorted(Path(input_dir).rglob("*.zip")):
        with zipfile.ZipFile(zip_fp) as z:
            for jf in safe_zip_members(z):
                if not jf.endswith(".json"):
                    continue
                with z.open(jf) as f:
                    try:
                        d = json.load(f)
                    except Exception:
                        continue
                meta = d.get("meta", {})
                if meta.get("source_language") != "ko":
                    continue
                texts = [str(s.get("source_cleaned", "")).strip() for s in d.get("sents", []) if str(s.get("source_cleaned", "")).strip()]
                merged = " ".join(texts)
                if len(merged) < 50:
                    continue
                prompt = f"다음 금융/법률 문서의 핵심 내용을 요약하세요:\n{merged[:600]}"
                sents = [s.strip() for s in re.split(r"[.\n]", merged) if len(s.strip()) > 10]
                completion = ". ".join(sents[:2]) + "." if sents else ""
                if len(completion) < 20:
                    continue
                rows.append(build_row(prompt, completion, "policy_sensitive", "aihub_금융", "금융", f"{zip_fp}/{jf}", f"fin_{len(rows):06d}"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=10000)
    args = ap.parse_args()
    rows = generate_rows(args.input_dir)[: args.target]
    write_jsonl(Path(args.output), rows)
    print("AIHUB_금융_LOAD_OK=1")
    print(f"AIHUB_금융_COUNT={len(rows)}")


if __name__ == "__main__":
    main()
