from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json
from collections import Counter
from pathlib import Path
from scripts.ai._aihub_common_v1 import REQUIRED_FIELDS, write_json, write_jsonl

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input', required=True); ap.add_argument('--output', required=True); ap.add_argument('--quarantine', required=True); ap.add_argument('--coverage-gap', required=True); args=ap.parse_args()
    rows=[json.loads(l) for l in Path(args.input).read_text(encoding='utf-8').splitlines() if l.strip()]
    q=[]; valid=[]; rc=Counter(); seen=set(); fcounts=Counter()
    for r in rows:
        reason=None
        for k in REQUIRED_FIELDS:
            if k not in r or r[k] in ('', None): reason='MISSING_FIELD'; break
        if not reason and not str(r.get('source','')).startswith('aihub_'): reason='INVALID_SOURCE'
        if not reason and r.get('split') not in ('train','validation'): reason='INVALID_SPLIT'
        if not reason and r['prompt'] in seen: reason='DUPLICATE_PROMPT'
        seen.add(r['prompt'])
        if not reason and r['function']=='tool_call':
            try: obj=json.loads(r['completion'])
            except Exception: reason='TOOL_JSON_INVALID'; obj=None
            if obj is not None and ('tool_name' not in obj or not isinstance(obj.get('arguments'), dict)): reason='TOOL_JSON_INVALID'
        if not reason and r['function']=='retrieval_transform':
            if '질문:' in r['completion'] or '답변:' in r['completion']: reason='MRC_NOT_ALLOWED'
            elif '이벤트' not in r['completion']: reason='RETRIEVAL_HALLUCINATION'
        if not reason and len(r['completion']) < 20: reason='COMPLETION_TOO_SHORT'
        if reason:
            x=dict(r); x['reason_code']=reason; q.append(x); rc[reason]+=1
        else:
            valid.append(r); fcounts[r['function']]+=1
    write_jsonl(Path(args.quarantine), q)
    targets={'dialogue':70000,'summarize':50000,'policy_sensitive':25000,'tool_call':30000,'retrieval_transform':30000,'rewrite':20000}
    gap={}
    for fn,target in targets.items():
        actual=fcounts.get(fn,0); gapv=max(0,target-actual); action='none' if actual>=target*0.5 else 'synthetic'
        gap[fn]={'target': target,'actual': actual,'gap': gapv,'action': action,'source_candidates': []}
    coverage_ok=all(v['actual'] >= v['target']*0.5 for v in gap.values())
    res={'valid_count': len(valid),'fail_count': len(q),'pass_rate': round(len(valid)/max(len(rows),1),4),'reason_code_distribution': dict(rc),'function_validation': {k:{'valid_count': fcounts.get(k,0)} for k in targets},'coverage_ok': coverage_ok,'all_pass': len(q)==0}
    write_json(Path(args.output), res); write_json(Path(args.coverage_gap), gap)
    if coverage_ok: print('AIHUB_FUNCTION_COVERAGE_OK=1')
    if res['pass_rate'] >= 0.95: print('AIHUB_VALIDATION_OK=1')
if __name__=='__main__': main()
