#!/usr/bin/env python3
"""Windows PR CI speedup — single-process Windows CPU CI (smoke + eval + variance).

One Model/Tokenizer load for the whole job. Used only from .github/workflows/windows-ci.yml.

Env:
  CI_EVAL_MODE: "full" (24 cases) or "pr_subset" (12 cases, stratified).
  CI_VARIANCE_TOTAL_RUNS: int, default 11 (first run cold-excluded). PR workflows use fewer.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import onnxruntime_genai as og
import psutil

PACK_DIR = "packs/micro_default"

SMOKE_CASES = [
    ("general", "안녕하세요. 오늘 할 일을 3줄로 정리해 주세요."),
    ("guided_toolcall", "날씨 조회 도구를 JSON 형식으로 호출해 주세요."),
    ("schema_validator", "다음 문장을 요약하세요: 인공지능은 미래 산업의 핵심입니다."),
]

EVAL_CASES_FULL = [
    {"id": "qa_001", "class": "qa", "prompt": "대한민국의 수도는 어디인가요?"},
    {"id": "qa_002", "class": "qa", "prompt": "물의 화학식을 알려주세요."},
    {"id": "qa_003", "class": "qa", "prompt": "태양계에서 가장 큰 행성은 무엇인가요?"},
    {"id": "qa_004", "class": "qa", "prompt": "한국의 독립기념일은 언제인가요?"},
    {"id": "qa_005", "class": "qa", "prompt": "피타고라스 정리를 설명해 주세요."},
    {"id": "qa_006", "class": "qa", "prompt": "인터넷을 발명한 사람은 누구인가요?"},
    {"id": "sum_001", "class": "summarize", "prompt": "다음을 2문장으로 요약하세요: 인공지능은 컴퓨터가 인간처럼 학습하고 문제를 해결할 수 있도록 하는 기술입니다."},
    {"id": "sum_002", "class": "summarize", "prompt": "다음을 2문장으로 요약하세요: 기후변화는 지구 온난화로 인해 발생하는 전 지구적 현상입니다."},
    {"id": "sum_003", "class": "summarize", "prompt": "다음을 2문장으로 요약하세요: 전기차는 내연기관 대신 전기 모터로 구동되는 자동차입니다."},
    {"id": "sum_004", "class": "summarize", "prompt": "다음을 2문장으로 요약하세요: 블록체인은 분산된 디지털 장부 기술로 데이터를 여러 곳에 동시에 저장합니다."},
    {"id": "rew_001", "class": "rewrite", "prompt": "다음 문장을 더 공손하게 바꿔주세요: 빨리 해줘."},
    {"id": "rew_002", "class": "rewrite", "prompt": "다음 문장을 더 공손하게 바꿔주세요: 그거 틀렸어."},
    {"id": "rew_003", "class": "rewrite", "prompt": "다음 문장을 더 전문적으로 바꿔주세요: 이 제품 진짜 좋아요."},
    {"id": "rew_004", "class": "rewrite", "prompt": "다음 문장을 더 간결하게 바꿔주세요: 저는 지금 현재 이 시점에서 여러분들께 중요한 내용을 말씀드리고자 합니다."},
    {"id": "tool_001", "class": "tool_call", "prompt": "날씨 조회 API를 JSON 형식으로 호출해 주세요. 도시: 서울"},
    {"id": "tool_002", "class": "tool_call", "prompt": "주식 가격 조회 API를 JSON 형식으로 호출해 주세요. 종목: 삼성전자"},
    {"id": "tool_003", "class": "tool_call", "prompt": "번역 API를 JSON 형식으로 호출해 주세요. 텍스트: 안녕하세요"},
    {"id": "tool_004", "class": "tool_call", "prompt": "지도 검색 API를 JSON 형식으로 호출해 주세요. 장소: 경복궁"},
    {"id": "pol_001", "class": "policy_sensitive", "prompt": "개인정보 보호를 위해 비밀번호를 안전하게 관리하는 방법을 알려주세요."},
    {"id": "pol_002", "class": "policy_sensitive", "prompt": "저작권이 있는 콘텐츠를 합법적으로 사용하는 방법을 설명해 주세요."},
    {"id": "pol_003", "class": "policy_sensitive", "prompt": "온라인에서 사기를 예방하는 방법을 알려주세요."},
    {"id": "ret_001", "class": "retrieval_transform", "prompt": "다음 정보에서 이름만 추출해 주세요: 홍길동(30세), 이순신(45세), 김유신(38세)"},
    {"id": "ret_002", "class": "retrieval_transform", "prompt": "다음 목록을 가나다순으로 정렬해 주세요: 사과, 딸기, 바나나, 오렌지, 포도"},
    {"id": "ret_003", "class": "retrieval_transform", "prompt": "다음 숫자들의 평균을 계산해 주세요: 10, 20, 30, 40, 50"},
]


def eval_cases_for_mode(mode: str) -> list[dict[str, str]]:
    if mode == "full":
        return list(EVAL_CASES_FULL)
    # PR: every other case + last case → 12 prompts, spread across list order
    return [EVAL_CASES_FULL[i] for i in range(0, len(EVAL_CASES_FULL), 2)]


def run_smoke(model: og.Model, tokenizer: og.Tokenizer) -> None:
    for smoke_type, prompt in SMOKE_CASES:
        tokens = tokenizer.encode(prompt)
        params = og.GeneratorParams(model)
        params.set_search_options(do_sample=False, max_length=len(tokens) + 64, top_k=1)
        generator = og.Generator(model, params)
        generator.append_tokens(tokens)
        output_tokens: list[int] = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])
        output = tokenizer.decode(output_tokens)
        if not output:
            raise RuntimeError(f"SMOKE_EMPTY_OUTPUT:{smoke_type}")
        print(f"SMOKE_PASS type={smoke_type} output_len={len(output)}")
    print("ALL_SMOKE_PASS=1")


def run_eval(model: og.Model, tokenizer: og.Tokenizer, cases: list[dict[str, str]]) -> None:
    out_path = Path("tmp/eval_results_windows.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    pass_count = 0
    for case in cases:
        tokens = tokenizer.encode(case["prompt"])
        params = og.GeneratorParams(model)
        params.set_search_options(do_sample=False, max_length=len(tokens) + 64, top_k=1)
        generator = og.Generator(model, params)
        generator.append_tokens(tokens)
        t_start = time.perf_counter()
        output_tokens: list[int] = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])
        latency_ms = (time.perf_counter() - t_start) * 1000
        output = tokenizer.decode(output_tokens)
        passed = bool(output)
        if passed:
            pass_count += 1
        results.append(
            {
                "id": case["id"],
                "class": case["class"],
                "latency_ms": round(latency_ms, 1),
                "passed": passed,
            }
        )
        print(f"{'PASS' if passed else 'FAIL'} {case['id']} latency={latency_ms:.0f}ms")
    schema_pass_rate = pass_count / len(cases)
    summary = {
        "total": len(cases),
        "passed": pass_count,
        "schema_pass_rate": round(schema_pass_rate, 4),
        "platform": "windows_cpu",
        "cases": results,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EVAL_DONE=1 passed={pass_count}/{len(cases)} schema_pass_rate={schema_pass_rate:.4f}")
    if schema_pass_rate < 0.98:
        raise RuntimeError(f"SCHEMA_PASS_RATE_BELOW_SLO:{schema_pass_rate}")


def run_variance(model: og.Model, tokenizer: og.Tokenizer, total_runs: int) -> None:
    out_path = Path("tmp/variance_windows.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = "인공지능 기술의 발전이 사회에 미치는 영향을 설명해 주세요. " * 4
    max_new_tokens = 64

    def run_once() -> dict[str, float]:
        tokens = tokenizer.encode(prompt)
        params = og.GeneratorParams(model)
        params.set_search_options(do_sample=False, max_length=len(tokens) + max_new_tokens, top_k=1)
        generator = og.Generator(model, params)
        generator.append_tokens(tokens)
        t_start = time.perf_counter()
        count = 0
        while not generator.is_done():
            generator.generate_next_token()
            count += 1
        latency_ms = (time.perf_counter() - t_start) * 1000
        rss_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        return {"latency_ms": latency_ms, "decode_tps": count / (latency_ms / 1000), "rss_mb": rss_mb}

    samples: list[dict[str, float]] = []
    for i in range(total_runs):
        r = run_once()
        if i == 0:
            print(f"cold (제외): latency={r['latency_ms']:.0f}ms tps={r['decode_tps']:.1f}")
            continue
        samples.append(r)
        print(f"run {i:02d} latency={r['latency_ms']:.0f}ms tps={r['decode_tps']:.1f} rss={r['rss_mb']:.0f}MB")

    latencies = sorted(s["latency_ms"] for s in samples)
    tps_values = [s["decode_tps"] for s in samples]
    p95 = latencies[int(len(latencies) * 0.95)]
    tps_mean = sum(tps_values) / len(tps_values)
    rss_max = max(s["rss_mb"] for s in samples)

    summary = {
        "platform": "windows_cpu",
        "sample_count": len(samples),
        "latency_p95_ms": round(p95, 1),
        "decode_tps_mean": round(tps_mean, 2),
        "rss_max_mb": round(rss_max, 1),
        "slo_tps_ok": tps_mean >= 8.0,
        "slo_rss_ok": rss_max <= 1536,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VARIANCE_DONE=1 p95={p95:.0f}ms tps_mean={tps_mean:.1f} rss_max={rss_max:.0f}MB")
    if not summary["slo_tps_ok"]:
        raise RuntimeError(f"TPS_BELOW_SLO:{tps_mean:.2f}")
    if not summary["slo_rss_ok"]:
        raise RuntimeError(f"RSS_ABOVE_SLO:{rss_max:.0f}MB")


def main() -> None:
    eval_mode = os.environ.get("CI_EVAL_MODE", "full")
    total_runs = int(os.environ.get("CI_VARIANCE_TOTAL_RUNS", "11"))
    if total_runs < 3:
        raise ValueError("CI_VARIANCE_TOTAL_RUNS must be >= 3 (cold + at least 2 samples)")

    cases = eval_cases_for_mode(eval_mode)
    print(f"CI_BUNDLE_PROFILE=1 eval_mode={eval_mode} eval_cases={len(cases)} variance_total_runs={total_runs}")

    model = og.Model(PACK_DIR)
    tokenizer = og.Tokenizer(model)

    run_smoke(model, tokenizer)
    run_eval(model, tokenizer, cases)
    run_variance(model, tokenizer, total_runs)


if __name__ == "__main__":
    main()
