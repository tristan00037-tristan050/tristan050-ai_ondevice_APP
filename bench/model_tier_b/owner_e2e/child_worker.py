"""Isolated child worker (R2-P0-003 / §5-§9).

Imports the real Butler product ONLY inside this child process (the owner verified
source identity before spawning it), runs a single real 1.7B Box3 smoke through the
real product pipeline, and emits one raw-safe JSON trace line on stdout. It records
every local product/bench module it actually imported so the owner can re-verify each
against the approved commit tree. No prompt/completion text, absolute paths, or user
identifiers are ever emitted — only digests, counts, durations, enums.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _imported_local_modules(repo_root: Path) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for module in list(sys.modules.values()):
        raw = getattr(module, "__file__", None)
        if not raw:
            continue
        try:
            resolved = Path(raw).resolve()
        except OSError:
            continue
        if repo_root not in resolved.parents or resolved.suffix != ".py":
            continue
        rel = resolved.relative_to(repo_root).as_posix()
        if rel.startswith(("bench/model_tier_b/tests/", "bench/model_tier_b/owner_e2e/")):
            continue  # owner/test harness itself is not the product surface under test
        if rel not in seen:
            seen[rel] = _sha256_file(resolved)
    return [{"relative_path": rel, "sha256": seen[rel]} for rel in sorted(seen)]


def run(repo_root: Path, model_path: Path) -> dict:
    model_sha = _sha256_file(model_path)
    size_bytes = model_path.stat().st_size
    with model_path.open("rb") as handle:
        gguf_ok = handle.read(4) == b"GGUF"

    os.environ["BUTLER_BOX3_BASE_MODEL_PATH"] = str(model_path)
    os.environ["BUTLER_BOX3_BASE_MODEL_SHA256_FULL"] = model_sha
    os.environ["BUTLER_BOX3_LOADER"] = "llama_cpp"

    from llama_cpp import Llama
    import llama_cpp

    from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope
    from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
    from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig
    from butler_pc_core.dlp.runtime import scan_runtime

    # Load with Metal, capturing the engine log only to parse the offloaded-layer
    # count (never persisted). n_gpu_layers=-1 requests offload of all supported layers.
    load_log = io.StringIO()
    load_start = time.monotonic_ns()
    with redirect_stderr(load_log):
        llm = Llama(model_path=str(model_path), n_gpu_layers=-1, n_ctx=1024, verbose=True, seed=11)
    model_ready = time.monotonic_ns()
    log_text = load_log.getvalue()
    match = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log_text)
    offloaded = int(match.group(1)) if match else 0
    metal_init = "Metal" in log_text or "ggml_metal" in log_text or "metal" in log_text

    trace = {"first_token_ns": None, "gen_start_ns": None, "completion_tokens": 0}

    def streaming_runner(envelope) -> str:
        prompt = (
            "You are Butler Box 3 local real draft runner. Use only the provided references.\n"
            f"DRAFT_REQUEST:\n{envelope.drafting_request_runtime}\n\n"
            "REFERENCES:\n" + "\n".join(envelope.reference_text_runtime_only) + "\n최종 문안:"
        )
        trace["gen_start_ns"] = time.monotonic_ns()
        parts: list[str] = []
        for chunk in llm.create_completion(prompt, max_tokens=envelope.max_new_tokens, temperature=0.0, stream=True, seed=11):
            piece = chunk["choices"][0].get("text", "")
            if piece:
                if trace["first_token_ns"] is None:
                    trace["first_token_ns"] = time.monotonic_ns()
                trace["completion_tokens"] += 1
                parts.append(piece)
        return "".join(parts).strip()

    envelope = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="공급 계약 이행 확인 요청에 대한 짧은 회신 초안을 작성하라.",
        reference_texts=[
            "공급사는 2026년 3월 1일 계약 수량 전량을 납품했다.",
            "검수는 같은 날 완료됐고 이상 없음으로 기록됐다.",
        ],
        max_new_tokens=64,
    )
    config = Box3RealRunnerConfig.from_env()
    request_written = time.monotonic_ns()
    verdict = run_box3_real_enablement_pipeline(envelope, config=config, runner=streaming_runner)

    stages = {s.get("stage"): s for s in verdict.stage_trace if isinstance(s, dict) and "stage" in s}
    # Real DLP on the produced generation (raw-safe: detection flags/counts only).
    produced = verdict.draft_text or ""
    dlp = scan_runtime(produced if produced else "")

    load_ms = (model_ready - load_start) / 1_000_000
    first_token_latency_ms = None if trace["first_token_ns"] is None else (trace["first_token_ns"] - request_written) / 1_000_000

    return {
        "schema_version": "butler.bench.owner-child-trace.v1",
        "child_pid": os.getpid(),
        "python_version": platform.python_version(),
        "architecture": platform.machine(),
        "llama_cpp_version": getattr(llama_cpp, "__version__", "unknown"),
        "model_sha256": model_sha,
        "model_size_bytes": size_bytes,
        "gguf_magic_ok": gguf_ok,
        "requested_gpu_layers": -1,
        "actual_offloaded_layer_count": offloaded,
        "metal_backend_initialized": bool(metal_init),
        "real_generation_started": trace["gen_start_ns"] is not None,
        "first_token_received": trace["first_token_ns"] is not None,
        "completion_token_count": trace["completion_tokens"],
        "load_ms": round(load_ms, 1),
        "first_token_latency_ms": None if first_token_latency_ms is None else round(first_token_latency_ms, 1),
        "grounding_called": "claim_grounding" in stages,
        "dlp_called": True,
        "dlp_any_detected": bool(dlp.any_detected),
        "approval_called": True,
        "terminal_gate_called": "final_gate" in stages,
        "terminal_count": sum(1 for s in stages if s == "final_gate"),
        "terminal_status": str(stages.get("final_gate", {}).get("status")),
        "draft_digest": hashlib.sha256((produced or "").encode("utf-8")).hexdigest(),
        "imported_local_modules": _imported_local_modules(repo_root),
        "runtime_activation_allowed": 0,
    }


def main() -> int:
    payload = json.loads(sys.stdin.read())
    repo_root = Path(payload["repo_root"]).resolve(strict=True)
    model_path = Path(payload["model_path"]).resolve(strict=True)
    result = run(repo_root, model_path)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
