from __future__ import annotations
import argparse, json, re
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from collections import defaultdict
from scripts.ai._aihub_common_v1 import try_get, normalize_text, build_row, jsonl_write, polite_present


def _doc_id(fp: Path) -> str:
    """파일명에서 문서 ID 추출 (상위 디렉토리 + 파일명 앞 4개 파트)."""
    return str(fp.parent) + '_' + '_'.join(fp.stem.split('_')[:4])


def _merged_to_row(doc_id: str, merged_text: str) -> dict | None:
    if len(merged_text) < 200:
        return None
    sentences = [s.strip() for s in re.split(r'[.\n]', merged_text) if len(s.strip()) > 10]
    if not sentences:
        return None
    completion = '. '.join(sentences[:2]) + '.'
    if len(completion) < 20:
        return None
    prompt = f"다음 문서를 3문장 이내로 요약하세요:\n{merged_text}"
    return build_row(prompt, completion, "summarize", "office", dataset_name="Office", source_file=doc_id, record_id=f"office_{abs(hash(doc_id))%10**8:08d}", quality_flags=[])


def load_records(input_dir: str):
    doc_texts: dict[str, list[str]] = defaultdict(list)
    input_path = Path(input_dir)
    for fp in input_path.rglob('*.json'):
        did = _doc_id(fp)
        try:
            with open(fp, encoding='utf-8') as f:
                d = json.load(f)
            li = d.get('learning_data_info', {})
            if isinstance(li, dict):
                text = li.get('plain_text', '').strip()
                if text:
                    doc_texts[did].append(text)
        except Exception:
            continue

    rows = []
    for did, texts in doc_texts.items():
        merged = ' '.join(texts)
        row = _merged_to_row(did, merged)
        if row:
            rows.append(row)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=20000)
    args = ap.parse_args()
    rows = load_records(args.input_dir)[:args.target]
    count = jsonl_write(args.output, rows)
    print("AIHUB_OFFICE_LOAD_OK=1")
    print(f"AIHUB_OFFICE_COUNT={count}")

if __name__ == "__main__":
    main()
