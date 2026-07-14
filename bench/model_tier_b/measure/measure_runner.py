"""Canonical measurement runner for the model-tier-B bench (M3 Max, owner-run).

Per approved model: cold(N)+warm(M) real llama.cpp/Metal runs with a fixed prompt and
seed, recording load_ms, TTFT, decode tokens/s, completion token count, Metal offloaded
layers, and peak RSS; then p50/p95 summaries and an observer off/on authoritative-output
byte-equality check. Emits one raw-safe JSON (digests/counts/durations only — no prompt,
completion text, absolute model path, or user identifier). Produces numbers only; no
performance ranking or model-tier judgement. RUNTIME_ACTIVATION_ALLOWED stays 0.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import statistics
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path

import psutil

_PROMPT = "공급 계약 이행 확인 요청에 대한 짧은 회신 초안을 한 문단으로 작성하라. 참조: 공급사는 2026년 3월 1일 계약 수량 전량을 납품했고 검수는 같은 날 완료됐다."
_MAX_TOKENS = 64
_SEED = 11
_COLD = 3
_WARM = 10


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def _load(model_path: str):
    from llama_cpp import Llama

    log = io.StringIO()
    start = time.monotonic_ns()
    with redirect_stderr(log):
        llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=1024, verbose=True, seed=_SEED)
    load_ms = (time.monotonic_ns() - start) / 1_000_000
    match = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log.getvalue())
    offloaded = int(match.group(1)) if match else 0
    metal = "Metal" in log.getvalue() or "ggml_metal" in log.getvalue()
    return llm, load_ms, offloaded, metal


def _generate(llm) -> dict:
    proc = psutil.Process()
    gen_start = time.monotonic_ns()
    first_token_ns = None
    last_token_ns = gen_start
    text_parts: list[str] = []
    for chunk in llm.create_completion(_PROMPT, max_tokens=_MAX_TOKENS, temperature=0.0, stream=True, seed=_SEED):
        piece = chunk["choices"][0].get("text", "")
        if piece:
            now = time.monotonic_ns()
            if first_token_ns is None:
                first_token_ns = now
            last_token_ns = now
            text_parts.append(piece)
    gen_end = time.monotonic_ns()
    completion = "".join(text_parts)
    n_tokens = len(text_parts)
    ttft_ms = None if first_token_ns is None else (first_token_ns - gen_start) / 1_000_000
    decode_span_s = max(1e-9, (last_token_ns - first_token_ns) / 1_000_000_000) if first_token_ns else 1e-9
    decode_tps = round((n_tokens - 1) / decode_span_s, 3) if n_tokens > 1 else 0.0
    return {
        "ttft_ms": None if ttft_ms is None else round(ttft_ms, 2),
        "completion_token_count": n_tokens,
        "decode_tokens_per_sec": decode_tps,
        "total_gen_ms": round((gen_end - gen_start) / 1_000_000, 2),
        "rss_bytes": proc.memory_info().rss,
        "output_digest": hashlib.sha256(completion.encode("utf-8")).hexdigest(),
    }


def measure_model(variant_id: str, model_path: Path) -> dict:
    resolved = model_path.resolve(strict=True)
    with resolved.open("rb") as handle:
        gguf_ok = handle.read(4) == b"GGUF"
    model_sha = _sha256_file(resolved)
    size_bytes = resolved.stat().st_size

    cold_load, cold_ttft, cold_tps, offloaded, metal_init, peak_rss, tokens = [], [], [], 0, False, 0, []
    for _ in range(_COLD):
        llm, load_ms, off, metal = _load(str(resolved))
        offloaded, metal_init = off, metal_init or metal
        gen = _generate(llm)
        cold_load.append(load_ms)
        if gen["ttft_ms"] is not None:
            cold_ttft.append(gen["ttft_ms"])
        cold_tps.append(gen["decode_tokens_per_sec"])
        peak_rss = max(peak_rss, gen["rss_bytes"])
        tokens.append(gen["completion_token_count"])
        del llm

    llm, warm_load_ms, off, metal = _load(str(resolved))
    offloaded, metal_init = off, metal_init or metal
    warm_ttft, warm_tps, warm_digests = [], [], set()
    for _ in range(_WARM):
        gen = _generate(llm)
        if gen["ttft_ms"] is not None:
            warm_ttft.append(gen["ttft_ms"])
        warm_tps.append(gen["decode_tokens_per_sec"])
        peak_rss = max(peak_rss, gen["rss_bytes"])
        tokens.append(gen["completion_token_count"])
        warm_digests.add(gen["output_digest"])

    # Observer off/on: fixed prompt/seed -> deterministic authoritative output digest.
    from butler_pc_core.model_tier_bench import observer

    observer.reset_failures()
    observer.clear_observer()
    off_digest = _generate(llm)["output_digest"]
    observer.set_observer(lambda event: None)
    on_digest = _generate(llm)["output_digest"]
    observer.clear_observer()
    del llm

    return {
        "variant_id": variant_id,
        "model_format": "GGUF",
        "gguf_magic_ok": gguf_ok,
        "sealed_model_sha256": model_sha,
        "model_size_bytes": size_bytes,
        "metal_backend_initialized": bool(metal_init),
        "actual_offloaded_layer_count": offloaded,
        "requested_gpu_layers": -1,
        "cold_runs": _COLD,
        "warm_runs": _WARM,
        "load_ms_cold_p50": _pct(cold_load, 50),
        "load_ms_cold_p95": _pct(cold_load, 95),
        "ttft_ms_cold_p50": _pct(cold_ttft, 50),
        "ttft_ms_cold_p95": _pct(cold_ttft, 95),
        "ttft_ms_warm_p50": _pct(warm_ttft, 50),
        "ttft_ms_warm_p95": _pct(warm_ttft, 95),
        "decode_tps_warm_p50": _pct(warm_tps, 50),
        "decode_tps_warm_p95": _pct(warm_tps, 95),
        "decode_tps_cold_p50": _pct(cold_tps, 50),
        "peak_rss_bytes": peak_rss,
        "peak_rss_mb": round(peak_rss / (1024 * 1024), 1),
        "completion_token_count_min": min(tokens),
        "completion_token_count_max": max(tokens),
        "warm_output_deterministic": len(warm_digests) == 1,
        "observer_off_on_authoritative_output_equal": off_digest == on_digest,
        "observer_emit_failures": len(observer.emit_failures()),
        "measurement_class": "FORMAL_M3_MEASUREMENT",
        "performance_ranking": "NOT_PERFORMED",
        "model_tier_judgement": "NOT_PERFORMED",
        "runtime_activation_allowed": 0,
    }


def main() -> int:
    spec = json.loads(sys.stdin.read())  # {"models": [{"variant_id":..., "path":...}, ...]}
    results = [measure_model(m["variant_id"], Path(m["path"])) for m in spec["models"]]
    payload = {
        "schema_version": "butler.bench.formal-measurement.v1",
        "host_architecture": os.uname().machine,
        "results": results,
        "g1_ready": False,
        "m4_ready": False,
        "m3_evidence_valid": False,
        "runtime_activation_allowed": 0,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
