"""ft_classifier.py — 방향 인식 + QLoRA PEFT 통합 분류기.

우선순위: PEFT(로드 성공 시) > 방향 오버라이드(D-2 C/D 결함 수정) > 규칙 기반.
PEFT base model(Qwen/Qwen3-4B ~8GB) 미캐시 시 graceful fail → 규칙+오버라이드로 동작.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .account_dict import match_account, ACCOUNT_BY_NAME

# ── 방향 감지 지표 ────────────────────────────────────────────────────────────
INCOME_INDICATORS: frozenset[str] = frozenset({
    "수입", "입금", "수령", "수취", "받음", "수금", "지급받",
})
EXPENSE_INDICATORS: frozenset[str] = frozenset({
    "납부", "지급", "지출", "결제", "구매", "구입", "비용", "지불",
})

# ── D-2 C/D 방향 오버라이드 맵 (expense account → income equivalent) ──────────
# 자문료/임대료 수입 시 지급 계정 대신 수익 계정으로 오버라이드
_INCOME_OVERRIDE: dict[str, Tuple[str, str, str]] = {
    "지급수수료": ("용역매출", "I_revenue", "+"),
    "지급임차료": ("임대수입", "VI_non_op_revenue", "+"),
}

# ── PEFT 어댑터 경로 후보 ─────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).parent / "models" / "qwen3_4b_accounting_v1"
_T7_DIR = Path(
    "/Volumes/T7 Shield/버틀러 트레이닝 데이터/회계데이터/06_models/qwen3_4b_accounting_v1"
)

_ADAPTER_CANDIDATES: list[Path] = [
    Path(os.environ["ACCOUNTING_ADAPTER_PATH"]) if "ACCOUNTING_ADAPTER_PATH" in os.environ else None,  # type: ignore[list-item]
    _MODEL_DIR,
    _T7_DIR,
]

# ── 런타임 PEFT 상태 ──────────────────────────────────────────────────────────
_peft_model = None
_peft_tokenizer = None
_peft_loaded: bool = False
_peft_attempted: bool = False


@dataclass
class ClassifyResult:
    category: str
    section: str
    sign: str
    confidence: float
    source: str  # "peft" | "direction_override" | "rule_base"


def _find_adapter() -> Optional[Path]:
    for p in _ADAPTER_CANDIDATES:
        if p and (p / "adapter_model.safetensors").exists():
            return p
    return None


def load_peft() -> bool:
    """PEFT 어댑터를 lazy 로드. 성공 시 True, 실패(base 미캐시 포함) 시 False."""
    global _peft_model, _peft_tokenizer, _peft_loaded, _peft_attempted
    if _peft_attempted:
        return _peft_loaded
    _peft_attempted = True
    if os.environ.get("ACCOUNTING_NO_PEFT"):
        return False

    adapter_path = _find_adapter()
    if adapter_path is None:
        return False

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        device = "mps" if torch.backends.mps.is_available() else "cpu"

        _peft_tokenizer = AutoTokenizer.from_pretrained(
            str(adapter_path), trust_remote_code=True
        )
        base = AutoModelForCausalLM.from_pretrained(
            "Qwen/Qwen3-4B", torch_dtype=torch.float16, trust_remote_code=True
        )
        _peft_model = PeftModel.from_pretrained(base, str(adapter_path))
        _peft_model = _peft_model.to(device).eval()
        _peft_loaded = True
        return True
    except Exception:
        return False


def _peft_infer(description: str, direction: str, amount: float) -> Optional[ClassifyResult]:
    """PEFT 모델 추론. 모델 미로드 또는 파싱 실패 시 None."""
    if not _peft_loaded:
        return None
    try:
        import torch

        prompt = (
            "<|im_start|>system\n당신은 한국 중소기업 회계 전문가입니다. "
            "거래 내역을 보고 적절한 계정과목을 분류하세요.\n<|im_end|>\n"
            f"<|im_start|>user\n거래 내역: {description}\n거래 방향: {direction}\n"
            f"금액: {int(amount):,}원\n계정과목을 분류하세요.\n<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        device = next(_peft_model.parameters()).device
        inputs = _peft_tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            out = _peft_model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=_peft_tokenizer.eos_token_id,
            )
        decoded = _peft_tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        m_cat = re.search(r"계정과목:\s*(.+)", decoded)
        m_sec = re.search(r"섹션:\s*(\S+)", decoded)
        m_sign = re.search(r"부호:\s*([+-])", decoded)
        m_conf = re.search(r"신뢰도:\s*(\d+)%", decoded)

        if not m_cat:
            return None

        return ClassifyResult(
            category=m_cat.group(1).strip(),
            section=m_sec.group(1) if m_sec else "other",
            sign=m_sign.group(1) if m_sign else "+",
            confidence=float(m_conf.group(1)) / 100 if m_conf else 0.80,
            source="peft",
        )
    except Exception:
        return None


def _detect_direction(text: str) -> Optional[str]:
    """텍스트에서 거래 방향 감지. 명확한 신호 없으면 None."""
    income = any(kw in text for kw in INCOME_INDICATORS)
    expense = any(kw in text for kw in EXPENSE_INDICATORS)
    if income and not expense:
        return "입금"
    if expense and not income:
        return "출금"
    return None  # 모호 또는 신호 없음


def ft_classify(
    description: str,
    vendor: str = "",
    amount: float = 0.0,
    direction: Optional[str] = None,
) -> ClassifyResult:
    """방향 인식 + PEFT 통합 분류 (drop-in 강화 버전).

    direction: 외부에서 알고 있으면 "입금"/"출금" 명시. None이면 텍스트에서 추론.
    """
    combined = f"{description} {vendor}".strip()

    # 방향 결정: 외부 제공 > 텍스트 추론
    if direction is None:
        direction = _detect_direction(combined) or "출금"  # 기본값: 출금(비용)

    is_income = direction == "입금"

    # 1. PEFT 추론 (lazy load, graceful fail)
    if not _peft_attempted:
        load_peft()
    peft_result = _peft_infer(description, direction, amount)
    if peft_result is not None and peft_result.category != "미분류":
        return peft_result

    # 2. 규칙 기반 분류
    category, confidence = match_account(description, vendor)

    # 3. 방향 오버라이드 — D-2 C/D 결함 수정
    if is_income and category in _INCOME_OVERRIDE:
        override_cat, override_sec, override_sign = _INCOME_OVERRIDE[category]
        return ClassifyResult(
            category=override_cat,
            section=override_sec,
            sign=override_sign,
            confidence=min(confidence, 0.80),
            source="direction_override",
        )

    # 4. 규칙 기반 결과
    acc = ACCOUNT_BY_NAME.get(category)
    return ClassifyResult(
        category=category,
        section=acc.section if acc else "other",
        sign=acc.sign if acc else "+",
        confidence=confidence,
        source="rule_base",
    )
