"""answer_cache.py — 답변 캐시 (TTL 1일)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from .base import BaseCache, _DEFAULT_DB

_TTL_1D = 1 * 24 * 3600


class AnswerCache(BaseCache):
    """
    키: sha256(prompt_template_id + input_digest + question + scenario)
    TTL: 1일
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        super().__init__(
            table="answer",
            db_path=db_path,
            ttl_seconds=_TTL_1D,
        )

    def build_key(
        self,
        *,
        prompt_template_id: str,
        input_digest: str,
        question: str,
        scenario: str = "",
    ) -> str:
        raw = f"{prompt_template_id}:{input_digest}:{question}:{scenario}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_answer(
        self,
        prompt_template_id: str,
        input_digest: str,
        question: str,
        scenario: str = "",
    ) -> Optional[str]:
        return self.get(
            self.build_key(
                prompt_template_id=prompt_template_id,
                input_digest=input_digest,
                question=question,
                scenario=scenario,
            )
        )

    def set_answer(
        self,
        prompt_template_id: str,
        input_digest: str,
        question: str,
        answer: str,
        scenario: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.set(
            self.build_key(
                prompt_template_id=prompt_template_id,
                input_digest=input_digest,
                question=question,
                scenario=scenario,
            ),
            answer,
            ttl_seconds=ttl_seconds,
        )
