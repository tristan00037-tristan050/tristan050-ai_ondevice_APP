#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, random, re, hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

LANG_KO_RE=re.compile(r"[가-힣]")
LANG_EN_RE=re.compile(r"[A-Za-z]")
DATASET_REGISTRY={"openassistant":{"path":"OpenAssistant/oasst1"},"dolly":{"path":"databricks/databricks-dolly-15k"},"koalpaca":{"path":"beomi/KoAlpaca-v1.1a"}}
FUNCTION_KEYWORDS={"summarize":["summarize","summary","요약"],"rewrite":["rewrite","rephrase","polite","concise","공손","다시 써","고쳐 써"],"retrieval_transform":["extract","json","정렬","sort","average","평균","key-value","key value"],"policy_sensitive":["password","confidential","approval","bypass","비밀번호","기밀","승인","우회"],"tool_call":["tool","json call","도구 호출"],"dialogue":["reply","draft","respond","answer","답장","응답"]}

def detect_lang(text:str)->str:
    has_ko=bool(LANG_KO_RE.search(text)); has_en=bool(LANG_EN_RE.search(text))
    if has_ko and has_en: return "mixed"
    if has_ko: return "ko"
    return "en"

def classify_function(text:str)->str:
    lowered=(text or "").lower()
    for fn, keys in FUNCTION_KEYWORDS.items():
        if any(k.lower() in lowered for k in keys): return fn
    return "dialogue"

def hash_record(rec:dict[str,Any])->str:
    return hashlib.sha256(json.dumps(rec, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def normalize_instruction_completion(source_name:str, prompt:str, completion:str):
    prompt=(prompt or "").strip(); completion=(completion or "").strip()
    if len(prompt) < 20: return None, "short_prompt"
    if len(prompt) > 1024: return None, "long_prompt"
    if len(completion) < 10: return None, "short_completion"
    rec={"prompt":prompt,"completion":completion,"function":classify_function(prompt),"lang":detect_lang(prompt+" "+completion),"format":"qwen2.5_chat","source":source_name}
    rec["record_digest_sha256"]=hash_record(rec)
    return rec, None

def normalize_dolly(row:dict[str,Any]):
    prompt=(row.get("instruction") or "").strip()
    context=(row.get("context") or "").strip()
    if context: prompt=f"{prompt}\n\nContext: {context}"
    completion=(row.get("response") or "").strip()
    return normalize_instruction_completion("dolly", prompt, completion)

def normalize_koalpaca(row:dict[str,Any]):
    instruction=(row.get("instruction") or "").strip()
    inp=(row.get("input") or "").strip()
    prompt=instruction if not inp else f"{instruction}\n\n입력: {inp}"
    completion=(row.get("output") or "").strip()
    return normalize_instruction_completion("koalpaca", prompt, completion)

def build_oasst_pairs(rows:list[dict[str,Any]], filter_stats:dict[str,dict[str,int]]):
    by_id={}
    for row in rows:
        msg_id=row.get("message_id") or row.get("id")
        if msg_id is not None: by_id[msg_id]=row
    pairs=[]
    for row in rows:
        if row.get("role") != "assistant":
            continue
        parent=by_id.get(row.get("parent_id"))
        if not parent:
            filter_stats["openassistant"]["missing_parent"] += 1
            continue
        if parent.get("role") != "prompter":
            filter_stats["openassistant"]["non_prompter_parent"] += 1
            continue
        prompt=(parent.get("text") or "").strip()
        completion=(row.get("text") or "").strip()
        rec, reason = normalize_instruction_completion("openassistant", prompt, completion)
        if rec is None:
            filter_stats["openassistant"][reason or "other"] += 1
            continue
        pairs.append(rec)
    return pairs

def dedupe(records:list[dict[str,Any]]):
    seen=set(); out=[]
    for rec in records:
        if rec["record_digest_sha256"] in seen: continue
        seen.add(rec["record_digest_sha256"]); out.append(rec)
    return out

def split_write(records:list[dict[str,Any]], out_dir:Path, function:str):
    total=len(records); train_n=int(total*0.8); val_n=int(total*0.1); test_n=total-train_n-val_n
    splits={"train":records[:train_n],"validation":records[train_n:train_n+val_n],"test":records[train_n+val_n:]}
    for split, rows in splits.items():
        path=out_dir/split/f"{function}.jsonl"; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows: f.write(json.dumps(row, ensure_ascii=False)+"\n")
    return {"train":train_n,"validation":val_n,"test":test_n}

def main():
    try:
        from datasets import load_dataset
    except ModuleNotFoundError as e:
        load_dataset = None
        import_error = str(e)
    else:
        import_error = None
    ap=argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="data/public")
    ap.add_argument("--skip-missing", action="store_true")
    args=ap.parse_args()
    random.seed(42)
    out_dir=Path(args.out_dir); collected=defaultdict(list); errors=[]; filter_stats=defaultdict(lambda: defaultdict(int))
    if load_dataset is None:
        if args.skip_missing:
            stats={"PUBLIC_DATA_OK":1,"errors":[{"dataset":"runtime","error":import_error}],"functions":{},"filtered_count":{}}
            Path("tmp").mkdir(exist_ok=True)
            Path("tmp/public_data_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
            print("PUBLIC_DATA_OK=1")
            return
        raise ModuleNotFoundError(import_error)
    for name, spec in DATASET_REGISTRY.items():
        try:
            ds=load_dataset(spec["path"], split="train")
        except Exception as e:
            if args.skip_missing:
                errors.append({"dataset":name,"error":str(e)}); continue
            raise
        if name=="openassistant":
            rows=[dict(r) for r in ds]
            for rec in build_oasst_pairs(rows, filter_stats):
                collected[rec["function"]].append(rec)
            continue
        for row in ds:
            row=dict(row)
            rec, reason = normalize_dolly(row) if name=="dolly" else normalize_koalpaca(row)
            if rec is None:
                filter_stats[name][reason or "other"] += 1
                continue
            collected[rec["function"]].append(rec)
    stats={"PUBLIC_DATA_OK":1,"errors":errors,"functions":{},"filtered_count":{k:dict(v) for k,v in filter_stats.items()}}
    for fn, rows in collected.items():
        rows=dedupe(rows); random.shuffle(rows); split_stats=split_write(rows, out_dir, fn); stats["functions"][fn]={"total":len(rows), **split_stats}
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/public_data_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PUBLIC_DATA_OK=1")

if __name__=="__main__":
    main()
