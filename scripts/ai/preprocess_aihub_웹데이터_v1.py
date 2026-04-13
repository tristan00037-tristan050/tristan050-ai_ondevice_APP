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
        try:
            z_obj = zipfile.ZipFile(zip_fp)
        except zipfile.BadZipFile:
            continue
        with z_obj as z:
            for jf in safe_zip_members(z):
                if not jf.endswith(".json"):
                    continue
                with z.open(jf) as f:
                    try:
                        d = json.load(f)
                    except Exception:
                        continue
                for ne in d.get("named_entity", []):
                    title_s = [t.get("sentence", "") for t in ne.get("title", []) if t.get("sentence", "").strip()]
                    content_s = [c.get("sentence", "") for c in ne.get("content", []) if c.get("sentence", "").strip()]
                    merged = " ".join(title_s + content_s)
                    if len(merged) < 200:
                        continue
                    prompt = f"다음 문서를 3문장 이내로 요약하세요:\n{merged[:600]}"
                    sents = [s.strip() for s in re.split(r"[.\n]", merged) if len(s.strip()) > 10]
                    completion = ". ".join(sents[:2]) + "." if sents else ""
                    if len(completion) < 20:
                        continue
                    rows.append(build_row(prompt, completion, "summarize", "aihub_웹데이터", "웹데이터", f"{zip_fp}/{jf}", f"web_{len(rows):06d}"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=20000)
    args = ap.parse_args()
    rows = generate_rows(args.input_dir)[: args.target]
    write_jsonl(Path(args.output), rows)
    print("AIHUB_웹데이터_LOAD_OK=1")
    print(f"AIHUB_웹데이터_COUNT={len(rows)}")


if __name__ == "__main__":
    main()
