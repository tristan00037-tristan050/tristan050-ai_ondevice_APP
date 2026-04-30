#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, datetime
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(description='Build a minimal AI/ML-BOM snapshot')
    ap.add_argument('--audit', required=True)
    ap.add_argument('--out', default='artifacts/mlbom_current_model.json')
    args = ap.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding='utf-8'))
    mlbom = {
        'bomFormat': 'CycloneDX',
        'specVersion': '1.6',
        'version': 1,
        'metadata': {
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'component': {
                'type': 'machine-learning-model',
                'name': 'butler_model_v1_adapter',
                'version': 'autobuilt'
            }
        },
        'components': [{
            'type': 'machine-learning-model',
            'name': audit['base_model'],
            'version': 'adapter-v1',
            'properties': [
                {'name': 'archive_sha256', 'value': audit['archive_sha256']},
                {'name': 'chat_template_sha256', 'value': audit['chat_template_sha256']},
                {'name': 'adapter_type', 'value': audit['adapter_type']}
            ]
        }]
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(mlbom, ensure_ascii=False, indent=2), encoding='utf-8')
    print('MLBOM_BUILD_OK=1')

if __name__ == '__main__':
    main()
