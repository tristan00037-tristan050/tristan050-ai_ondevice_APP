from __future__ import annotations

import inspect
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List


THRESHOLDS = {
    "bleu4": 0.15,
    "rouge_l": 0.30,
    "avg_latency_sec": 10.0,
}

FAIL_BLEU = "EVAL_FAIL_BLEU"
FAIL_ROUGE = "EVAL_FAIL_ROUGE"
FAIL_LATENCY = "EVAL_FAIL_LATENCY"
FAIL_EMPTY_RESPONSE = "EVAL_FAIL_EMPTY_RESPONSE"
FAIL_TIMEOUT = "EVAL_FAIL_TIMEOUT"
FAIL_EXCEPTION = "EVAL_FAIL_EXCEPTION"
FAIL_RESPONSE_TOO_LONG = "EVAL_FAIL_RESPONSE_TOO_LONG"
FAIL_NO_EVAL_DATA = "EVAL_FAIL_NO_EVAL_DATA"


@dataclass
class BasicEvalResult:
    bleu4: float
    rouge_l: float
    avg_latency_sec: float
    avg_response_length: float
    sample_count: int
    passed: bool
    fail_reasons: List[str]
    error_counts: Dict[str, int] = field(default_factory=dict)
    sample_failures: List[dict] = field(default_factory=list)


def _tokens(text: str) -> List[str]:
    return [tok for tok in (text or "").split() if tok]


def compute_bleu4(hyp: str, ref: str) -> float:
    h, r = _tokens(hyp), _tokens(ref)
    if not h or not r:
        return 0.0

    max_order = min(4, len(h), len(r))
    precisions: List[float] = []
    for n in range(1, max_order + 1):
        hgrams = Counter(tuple(h[i:i+n]) for i in range(len(h) - n + 1))
        rgrams = Counter(tuple(r[i:i+n]) for i in range(len(r) - n + 1))
        total = sum(hgrams.values())
        if total == 0:
            return 0.0
        matches = sum((hgrams & rgrams).values())
        precisions.append(matches / total)

    if any(p <= 0 for p in precisions):
        return 0.0
    brevity_penalty = 1.0 if len(h) > len(r) else math.exp(1.0 - (len(r) / max(len(h), 1)))
    return brevity_penalty * math.exp(sum(math.log(p) for p in precisions) / max_order)


def compute_rouge_l(hyp: str, ref: str) -> float:
    h, r = _tokens(hyp), _tokens(ref)
    if not h or not r:
        return 0.0

    m, n = len(r), len(h)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        ri = r[i - 1]
        for j in range(1, n + 1):
            if ri == h[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs = dp[m][n]
    precision = lcs / n if n else 0.0
    recall = lcs / m if m else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _is_qwen3(model: Any, tokenizer: Any) -> bool:
    tokenizer_name = getattr(tokenizer, "name_or_path", "") or ""
    model_type = getattr(getattr(model, "config", None), "model_type", "") or ""
    return "qwen3" in tokenizer_name.lower() or model_type == "qwen3"


def _infer_device(model: Any):
    try:
        import torch
        if hasattr(model, "device"):
            return model.device
        if hasattr(model, "parameters"):
            return next(model.parameters()).device
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    except Exception:
        return "cpu"


def generate_eval_response(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    max_new_tokens: int = 256,
    timeout_sec: float = 10.0,
) -> str:
    """Shared deterministic generation helper for evaluations."""
    if hasattr(model, "generate_text"):
        return str(model.generate_text(prompt=prompt, max_new_tokens=max_new_tokens, timeout_sec=timeout_sec))

    if model is None or tokenizer is None:
        raise ValueError("model/tokenizer가 필요합니다")

    use_qwen3 = _is_qwen3(model, tokenizer)
    messages = [{"role": "user", "content": prompt}]

    if hasattr(tokenizer, "apply_chat_template"):
        sig = inspect.signature(tokenizer.apply_chat_template)
        template_kwargs = {"tokenize": False, "add_generation_prompt": True}
        if use_qwen3 and "enable_thinking" in sig.parameters:
            template_kwargs["enable_thinking"] = False
        rendered_prompt = tokenizer.apply_chat_template(messages, **template_kwargs)
        enc = tokenizer(rendered_prompt, return_tensors="pt", add_special_tokens=False)
    else:
        enc = tokenizer(prompt, return_tensors="pt")

    try:
        import torch
        device = _infer_device(model)
        enc = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in enc.items()}
        if "attention_mask" not in enc and "input_ids" in enc:
            enc["attention_mask"] = torch.ones_like(enc["input_ids"])
    except Exception:
        pass

    gen_kwargs = {
        **enc,
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
    }
    if use_qwen3:
        gen_kwargs["enable_thinking"] = False

    outputs = model.generate(**gen_kwargs)
    input_ids = enc["input_ids"]
    input_len = input_ids.shape[-1] if hasattr(input_ids, "shape") else len(input_ids[0])
    generated = outputs[0][input_len:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def run_basic_eval(
    model: Any,
    tokenizer: Any,
    eval_records: List[dict],
    dry_run: bool = False,
    *,
    timeout_sec: float = 10.0,
    max_response_tokens: int = 1024,
) -> BasicEvalResult:
    if dry_run:
        return BasicEvalResult(
            bleu4=0.99,
            rouge_l=0.99,
            avg_latency_sec=1.0,
            avg_response_length=100.0,
            sample_count=0,
            passed=True,
            fail_reasons=[],
            error_counts={"exceptions": 0, "empty_responses": 0, "timeouts": 0, "too_long": 0},
        )

    if not eval_records:
        return BasicEvalResult(
            bleu4=0.0,
            rouge_l=0.0,
            avg_latency_sec=0.0,
            avg_response_length=0.0,
            sample_count=0,
            passed=False,
            fail_reasons=[FAIL_NO_EVAL_DATA],
            error_counts={"exceptions": 0, "empty_responses": 0, "timeouts": 0, "too_long": 0},
        )

    bleus: List[float] = []
    rouges: List[float] = []
    latencies: List[float] = []
    lengths: List[int] = []
    error_counts: Dict[str, int] = {"exceptions": 0, "empty_responses": 0, "timeouts": 0, "too_long": 0}
    sample_failures: List[dict] = []

    for rec in eval_records:
        prompt = str(rec.get("prompt", ""))
        reference = str(rec.get("completion", ""))
        case_id = str(rec.get("case_id", "unknown"))
        started = time.time()
        try:
            response = generate_eval_response(
                model,
                tokenizer,
                prompt,
                max_new_tokens=min(256, max_response_tokens),
                timeout_sec=timeout_sec,
            )
            elapsed = time.time() - started
            latencies.append(elapsed)

            if elapsed > timeout_sec:
                error_counts["timeouts"] += 1
                sample_failures.append({"case_id": case_id, "reason": FAIL_TIMEOUT})
                bleus.append(0.0)
                rouges.append(0.0)
                lengths.append(0)
                continue

            response = (response or "").strip()
            token_len = len(_tokens(response))

            if not response:
                error_counts["empty_responses"] += 1
                sample_failures.append({"case_id": case_id, "reason": FAIL_EMPTY_RESPONSE})
                bleus.append(0.0)
                rouges.append(0.0)
                lengths.append(0)
                continue

            if token_len > max_response_tokens:
                error_counts["too_long"] += 1
                sample_failures.append(
                    {"case_id": case_id, "reason": FAIL_RESPONSE_TOO_LONG, "response_tokens": token_len}
                )
                bleus.append(0.0)
                rouges.append(0.0)
                lengths.append(token_len)
                continue

            bleus.append(compute_bleu4(response, reference))
            rouges.append(compute_rouge_l(response, reference))
            lengths.append(token_len)

        except TimeoutError:
            error_counts["timeouts"] += 1
            sample_failures.append({"case_id": case_id, "reason": FAIL_TIMEOUT})
            bleus.append(0.0)
            rouges.append(0.0)
            latencies.append(timeout_sec)
            lengths.append(0)
        except Exception as exc:
            error_counts["exceptions"] += 1
            sample_failures.append({"case_id": case_id, "reason": FAIL_EXCEPTION, "detail": str(exc)})
            bleus.append(0.0)
            rouges.append(0.0)
            latencies.append(timeout_sec)
            lengths.append(0)

    bleu4 = sum(bleus) / max(len(bleus), 1)
    rouge_l = sum(rouges) / max(len(rouges), 1)
    avg_latency = sum(latencies) / max(len(latencies), 1)
    avg_response_length = sum(lengths) / max(len(lengths), 1)

    fail_reasons: List[str] = []
    if bleu4 < THRESHOLDS["bleu4"]:
        fail_reasons.append(f"{FAIL_BLEU}:{bleu4:.3f}")
    if rouge_l < THRESHOLDS["rouge_l"]:
        fail_reasons.append(f"{FAIL_ROUGE}:{rouge_l:.3f}")
    if avg_latency > THRESHOLDS["avg_latency_sec"]:
        fail_reasons.append(f"{FAIL_LATENCY}:{avg_latency:.3f}")
    if error_counts["empty_responses"] > 0:
        fail_reasons.append(f"{FAIL_EMPTY_RESPONSE}:{error_counts['empty_responses']}")
    if error_counts["timeouts"] > 0:
        fail_reasons.append(f"{FAIL_TIMEOUT}:{error_counts['timeouts']}")
    if error_counts["exceptions"] > 0:
        fail_reasons.append(f"{FAIL_EXCEPTION}:{error_counts['exceptions']}")
    if error_counts["too_long"] > 0:
        fail_reasons.append(f"{FAIL_RESPONSE_TOO_LONG}:{error_counts['too_long']}")

    return BasicEvalResult(
        bleu4=bleu4,
        rouge_l=rouge_l,
        avg_latency_sec=avg_latency,
        avg_response_length=avg_response_length,
        sample_count=len(eval_records),
        passed=len(fail_reasons) == 0,
        fail_reasons=fail_reasons,
        error_counts=error_counts,
        sample_failures=sample_failures[:20],
    )
