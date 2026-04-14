from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from pathlib import Path
from scripts.ai._anthropic_common_v1 import read_jsonl, save_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', nargs='+', required=True)
    ap.add_argument('--validation-json', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--batch-id', default='manual')
    args = ap.parse_args()

    rows = []
    for p in args.inputs:
        rows.extend(read_jsonl(Path(p)))
    validation = json.loads(Path(args.validation_json).read_text(encoding='utf-8'))
    manifest = {
        'model_id': args.model_id,
        'batch_id': args.batch_id,
        'line_count': len(rows),
        'token_usage': {
            'input_tokens': sum(max(1, len(r['prompt']) // 3) for r in rows),
            'output_tokens': sum(max(1, len(r['completion']) // 3) for r in rows),
        },
        'validation_summary': validation,
        'by_task_type': {},
    }
    for row in rows:
        manifest['by_task_type'][row['task_type']] = manifest['by_task_type'].get(row['task_type'], 0) + 1
    save_json(Path(args.output), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
