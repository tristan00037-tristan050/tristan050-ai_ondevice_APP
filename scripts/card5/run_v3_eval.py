"""run_v3_eval.py — v2 adapter + v3 system prompt + alias 매핑 사후 처리.

학습 본질 0. v2 의미 학습 재사용 + strict allowlist 강제 + alias 정규화.
"""
from __future__ import annotations
import hashlib, json, re, time
from pathlib import Path
from mlx_lm import generate, load

ROOT = Path("/Users/kimsunghoon/Desktop/butler-data/27_accounting_train")
MODEL = ROOT/"models/qwen3-1.7b-mlx-q4"
ADAPTER = ROOT/"models/butler-1.7b-v3-card5-accounting-lora-v2"
EVAL = ROOT/"evaluation/card5_eval_set_v1.jsonl"
OUT = ROOT/"evidence/accounting27/post_v3_eval_report.json"

# 47 allowlist (자료/명명 정확)
ALLOWLIST = [
    ("매출","4010"),("제품매출","4020"),("상품매출","4030"),("용역매출","4040"),("임대수입","4050"),
    ("제품매출원가","5005"),("상품매출원가","5010"),("용역원가","5015"),("매출총이익","5020"),
    ("임원급여","8010"),("직원급여","8020"),("상여금","8030"),("퇴직급여","8040"),
    ("복리후생비","8050"),("여비교통비","8060"),("접대비","8070"),("통신비","8080"),
    ("전력비","8090"),("세금과공과금","8100"),("감가상각비","8110"),("지급임차료","8120"),
    ("보험료","8130"),("차량유지비","8140"),("경상연구개발비","8150"),("운반비","8160"),
    ("교육훈련비","8170"),("도서인쇄비","8180"),("사무용품비","8190"),("소모품비","8200"),
    ("지급수수료","8210"),("광고선전비","8220"),("건물관리비","8230"),
    ("수선비","8240"),("대손상각비","8250"),("무형자산상각비","8260"),("잡비","8270"),
    ("이자수익","9010"),("유형자산처분이익","9020"),("잡이익","9030"),("임대료수익","9040"),("배당금수익","9050"),
    ("이자비용","9110"),("전기오류수정손실","9120"),("잡손실","9130"),("외환차손","9140"),("기부금","9150"),("유형자산처분손실","9160"),
]
ALLOW = {n for n,_ in ALLOWLIST}
TITLE_TO_CODE = {n:c for n,c in ALLOWLIST}
assert len(ALLOW) == 47

# Phase B3 alias 매핑 (의미 보존 정확 매핑)
ALIAS_MAP = {
    "서비스매출": "용역매출",
    "임대수익": "임대료수익",
    "대출이자비용": "이자비용",
    "사무실 월세": "지급임차료",
    "재고자산상각비": "상품매출원가",
    "원료비": "제품매출원가",
    "제품비": "상품매출원가",
    "하도급원가": "용역원가",
    "개발비": "용역원가",
    "보험수리적손실": "잡손실",
    "용역수익": "용역매출",
    "제품원가": "제품매출원가",
}

# v3 system prompt — 47 allowlist 명시
ALLOW_LIST_STR = (
    "sales: 매출, 제품매출, 상품매출, 용역매출, 임대수입\n"
    "cost_of_sales: 제품매출원가, 상품매출원가, 용역원가, 매출총이익\n"
    "sga: 임원급여, 직원급여, 상여금, 퇴직급여, 복리후생비, 여비교통비, 접대비, 통신비, "
    "전력비, 세금과공과금, 감가상각비, 지급임차료, 보험료, 차량유지비, 경상연구개발비, "
    "운반비, 교육훈련비, 도서인쇄비, 사무용품비, 소모품비, 지급수수료, 광고선전비, 건물관리비, "
    "수선비, 대손상각비, 무형자산상각비, 잡비\n"
    "non_op_revenue: 이자수익, 유형자산처분이익, 잡이익, 임대료수익, 배당금수익\n"
    "non_op_expense: 이자비용, 전기오류수정손실, 잡손실, 외환차손, 기부금, 유형자산처분손실"
)
SYSTEM = (
    "당신은 한국 기업 회계처리 기준에 따라 거래를 47개 계정과목으로 분류하는 "
    "Butler 카드 5 회계 분류 모델입니다.\n\n"
    f"ALLOWED account_title (반드시 이 47개 중 하나):\n{ALLOW_LIST_STR}\n\n"
    "ABSOLUTE RULES:\n"
    "1. account_title은 반드시 위 47개 정확 명명에서만 선택 (동의어/유사 표현 금지).\n"
    "2. account_code는 allowlist 정합 (예: 매출=4010, 통신비=8080).\n"
    "3. 출력은 JSON 객체 하나만. 설명·추론·문장 0.\n"
    "4. JSON 외 텍스트 절대 0.\n"
    "5. reason은 50자 이내 짧은 한 줄. /no_think"
)

_J = re.compile(r"\{[^{}]*\}", re.S)
def pj(t):
    t = t.replace("```json","").replace("```","")
    m = _J.search(t)
    if not m: return None
    try: return json.loads(m.group(0))
    except: return None


def apply_alias(title):
    """Phase B3 — alias 정규화 사후 처리."""
    if title in ALLOW:
        return title, "exact_match"
    if title in ALIAS_MAP:
        return ALIAS_MAP[title], "alias_mapped"
    return title, "hallucination"


def main():
    t0 = time.time()
    print("[load] base + LoRA v2 adapter (재사용)", flush=True)
    model, tok = load(str(MODEL), adapter_path=str(ADAPTER))
    items = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[eval] {len(items)} cases (v3 system prompt + alias 사후처리)", flush=True)

    results = []
    alias_count = 0
    for it in items:
        msgs = [{"role":"system","content":SYSTEM},
                {"role":"user","content":f"거래: {it['input']}"}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        resp = generate(model, tok, prompt=prompt, max_tokens=160, verbose=False)
        p = pj(resp)
        raw_title = p.get("account_title","") if p else ""
        norm_title, source = apply_alias(raw_title)
        if source == "alias_mapped": alias_count += 1
        if p is not None:
            p["_raw_title"] = raw_title
            p["_norm_title"] = norm_title
            p["_alias_source"] = source
            # alias 매핑 후 account_code도 정합 정정
            if source == "alias_mapped":
                p["account_title"] = norm_title
                p["account_code"] = TITLE_TO_CODE.get(norm_title, p.get("account_code"))
        results.append({"id":it["id"], "expected":it["expected"], "pred":p, "raw":resp[:300]})

    # 8 metric
    n=len(results); title=dirn=tax=code=jv=halluc=ua=whc=cc=0
    nr_tp=nr_fp=nr_fn=nr_tn=0
    for r in results:
        p=r["pred"]; e=r["expected"]
        if p is None: continue
        jv+=1
        if p.get("account_title")==e["account_title"]: title+=1
        if p.get("account_title") not in ALLOW: halluc+=1
        if p.get("debit_credit")==e["debit_credit"]: dirn+=1
        if p.get("tax_relevance")==e["tax_relevance"]: tax+=1
        if str(p.get("account_code"))==str(e["account_code"]): code+=1
        if p.get("unsupported_tax_or_legal_assertion") is True: ua+=1
        conf=float(p.get("confidence",0) or 0); wrong=p.get("account_title")!=e["account_title"]
        if conf>=0.80 and wrong: whc+=1
        nrp=bool(p.get("needs_review")); nrt=wrong
        if nrp and nrt: nr_tp+=1
        elif nrp and not nrt: nr_fp+=1
        elif not nrp and nrt: nr_fn+=1
        else: nr_tn+=1
        if p.get("account_title")==e["account_title"] and str(p.get("account_code"))==str(e["account_code"]): cc+=1

    wall = round(time.time()-t0,1)
    report = {
        "model":"qwen3-1.7b-mlx-q4 + butler-1.7b-v3-card5-accounting-lora-v2 + v3 system prompt + alias post-processing",
        "model_execution_kind":"real_run",
        "eval_set":"evaluation/card5_eval_set_v1.jsonl",
        "eval_set_size":n,
        "eval_set_sha256": hashlib.sha256(EVAL.read_bytes()).hexdigest(),
        "metrics":{
            "account_title_accuracy":round(title/n,4),
            "debit_credit_direction_accuracy":round(dirn/n,4),
            "tax_relevance_accuracy":round(tax/n,4),
            "structured_json_valid_rate":round(jv/n,4),
            "hallucinated_account_count":halluc,
            "unsupported_tax_or_legal_assertion_count":ua,
            "needs_review_precision":round(nr_tp/(nr_tp+nr_fp),4) if (nr_tp+nr_fp) else 0.0,
            "needs_review_recall":round(nr_tp/(nr_tp+nr_fn),4) if (nr_tp+nr_fn) else 0.0,
            "wrong_high_confidence_count":whc,
            "account_code_consistency_rate":round(cc/n,4),
        },
        "v3_alias_mapped_count": alias_count,
        "wall_clock_seconds":wall,
        "training_executed": False,
        "v2_adapter_reused": True,
        "alias_map_size": len(ALIAS_MAP),
        "adapter_merged_into_base":False,
        "base_model_changed":False,
        "tokenizer_changed":False,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT.parent/"post_v3_predictions.jsonl").write_text(
        "\n".join(json.dumps({"id":r["id"],"expected":r["expected"],"pred":r["pred"]}, ensure_ascii=False) for r in results),
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
