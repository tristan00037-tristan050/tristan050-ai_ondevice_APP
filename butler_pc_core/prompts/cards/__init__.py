"""카드 프롬프트 YAML 로더."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_CARDS_DIR = Path(__file__).resolve().parent

_CARD_FILES: dict[int, str] = {
    1: "card_01_request_parse.yaml",
    2: "card_02_external_to_our_format.yaml",
    3: "card_03_new_draft_from_past.yaml",
    4: "card_04_document_review.yaml",
    5: "card_05_bank_to_accounting.yaml",
    6: "card_06_fill_external_form.yaml",
}

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_FREE_CARD: dict[str, Any] = {
    "card_id": "free",
    "title": "자유 입력",
    "system_prompt": "버틀러(Butler)는 기업이 쓸수록 그 회사에 맞춰가는 기업용 온디바이스 AI 업무 OS입니다. 인터넷 연결 없이 사용자 기기 안에서 동작하고, 회사 데이터는 기기 밖으로 보내지 않습니다. 회사 내부 사실이나 모르는 정보는 지어내지 말고 '확인이 필요하다'고 솔직히 답하세요. 답변은 자연스러운 한국어 문단으로 간결하게 쓰고, 제목(##)·구분선(---)·굵게(**)는 최소화하세요.",
    "user_prompt_template": "{{ query }}",
}


def load_card_prompt(card_mode: int | str) -> dict[str, Any]:
    """card_mode(int 1-6 또는 'free')에 해당하는 YAML을 로드하여 dict 반환.

    Raises: FileNotFoundError, ValueError
    """
    if card_mode in ("free", 0, "0"):
        return _FREE_CARD.copy()

    try:
        mode_int = int(card_mode)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"card_mode must be 1-6 or 'free', got {card_mode!r}") from exc

    fname = _CARD_FILES.get(mode_int)
    if fname is None:
        raise ValueError(f"Unknown card_mode: {mode_int}")

    path = _CARDS_DIR / fname
    if not path.exists():
        raise FileNotFoundError(f"Card YAML not found: {path}")

    if not _YAML_AVAILABLE:
        return {
            "card_id": f"card_{mode_int:02d}",
            "system_prompt": "당신은 사무 보조 AI입니다.",
            "user_prompt_template": "{{ query }}",
        }

    with path.open(encoding="utf-8") as f:
        return _yaml.safe_load(f)
