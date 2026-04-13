from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, ast, json, zipfile

from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl


def generate_rows(input_dir: str):
    rows = []
    for zip_fp in sorted(Path(input_dir).rglob("TL*.zip")):
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
                data = d.get("data", {})
                if not isinstance(data, dict):
                    continue
                text = str(data.get("text", "")).strip()
                events = data.get("event", [])
                if isinstance(events, str):
                    try:
                        events = ast.literal_eval(events)
                    except Exception:
                        continue
                sents = [e.get("sentence", "").strip() for e in events if isinstance(e, dict) and e.get("sentence", "").strip()]
                if not text or not sents:
                    continue
                if any(s[:10] not in text for s in sents[:3]):
                    continue
                completion = "\n".join(f"이벤트 {i+1}: {s}" for i, s in enumerate(sents[:3]))
                prompt = f"다음 기사에서 주요 이벤트를 추출하세요.\n\n기사: {text[:500]}"
                rows.append(build_row(prompt, completion, "retrieval_transform", "aihub_event", "이벤트", f"{zip_fp}/{jf}", f"event_{len(rows):06d}"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=30000)
    args = ap.parse_args()
    rows = generate_rows(args.input_dir)[: args.target]
    write_jsonl(Path(args.output), rows)
    print("AIHUB_이벤트_LOAD_OK=1")
    print(f"AIHUB_이벤트_COUNT={len(rows)}")


if __name__ == "__main__":
    main()
