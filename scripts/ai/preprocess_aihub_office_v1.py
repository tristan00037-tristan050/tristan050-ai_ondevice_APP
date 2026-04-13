from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json, re, zipfile
from collections import defaultdict

from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl


def generate_rows(input_dir: str):
    rows = []
    docs = defaultdict(list)
    for zip_fp in sorted(Path(input_dir).rglob("TL*.zip")):
        try:
            z_obj = zipfile.ZipFile(zip_fp)
        except zipfile.BadZipFile:
            continue
        with z_obj as z:
            for jf_raw in z.namelist():
                jf = jf_raw.lstrip("/")
                if not jf.endswith(".json"):
                    continue
                stem = Path(jf).stem
                doc_id = str(zip_fp) + "_" + "_".join(stem.split("_")[:4])
                with z.open(jf_raw) as f:
                    try:
                        d = json.load(f)
                    except Exception:
                        continue
                li = d.get("learning_data_info", {})
                text = li.get("plain_text", "").strip() if isinstance(li, dict) else ""
                if text:
                    docs[doc_id].append(text)
    for did, texts in docs.items():
        merged = " ".join(texts)
        if len(merged) < 40:
            continue
        prompt = "다음 문장을 고객 친화적이고 공손한 톤으로 다시 써주세요:\n" + merged[:500]
        sentences = [s.strip() for s in re.split(r"[.\n]", merged) if len(s.strip()) > 10]
        completion = ". ".join(sentences[:2]) + "." if sentences else ""
        if len(completion) < 20:
            continue
        rows.append(build_row(prompt, completion, "rewrite", "aihub_office", "오피스", did, f"office_{len(rows):06d}"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=10000)
    args = ap.parse_args()
    rows = generate_rows(args.input_dir)[: args.target]
    write_jsonl(Path(args.output), rows)
    print("AIHUB_오피스_LOAD_OK=1")
    print(f"AIHUB_오피스_COUNT={len(rows)}")


if __name__ == "__main__":
    main()
