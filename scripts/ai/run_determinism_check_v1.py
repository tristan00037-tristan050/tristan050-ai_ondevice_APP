from __future__ import annotations

from .phase_c_shared import sha256_16


def run_determinism(outputs: list[str]) -> tuple[bool, str]:
    digests = [sha256_16(o) for o in outputs]
    ok = len(set(digests)) == 1
    return ok, digests[0] if digests else ''


def run_determinism_with_model(model, tokenizer, prompt: str, seed: int = 42, n: int = 3) -> tuple[bool, str]:
    """실제 모델 추론을 n회 실행하여 출력 digest가 일치하는지 확인한다."""
    import torch

    outputs: list[str] = []
    messages = [{'role': 'user', 'content': prompt}]
    for _ in range(n):
        tokenized = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors='pt',
            enable_thinking=False,
        )
        tokenized = tokenized.to(model.device)
        with torch.no_grad():
            out = model.generate(
                tokenized,
                max_new_tokens=64,
                temperature=0.0,
                do_sample=False,
            )
        text = tokenizer.decode(out[0][tokenized.shape[1]:], skip_special_tokens=True).strip()
        outputs.append(text)
    return run_determinism(outputs)
