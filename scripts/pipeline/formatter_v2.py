from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


SYSTEM_PROMPT = (
    "당신은 버틀러입니다. 기업용 온디바이스 AI 어시스턴트로서 정확하고 "
    "신뢰할 수 있는 답변을 제공합니다."
)


@dataclass
class TrainingRecord:
    prompt: str
    completion: str
    domain: str
    quality_score: float
    source: str
    output_digest_sha256: str


class DataFormatter:
    def __init__(self, system_prompt: str = SYSTEM_PROMPT):
        self.system_prompt = system_prompt

    def validate_template(self, tokenizer) -> bool:
        try:
            tokenizer.apply_chat_template(
                [{"role": "user", "content": "test"}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def format_document(
        self,
        text: str,
        domain: str,
        quality_score: float,
        source: str,
    ) -> Optional[TrainingRecord]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 3:
            return None

        split_index = max(1, int(round(len(lines) * 0.67)))
        prompt_body = "\n".join(lines[:split_index]).strip()
        completion = "\n".join(lines[split_index:]).strip()
        if not prompt_body or not completion:
            return None

        prompt = (
            "다음 내용을 읽고 이어지는 내용을 작성하세요:\n\n"
            f"{prompt_body}"
        )
        return TrainingRecord(
            prompt=prompt,
            completion=completion,
            domain=domain,
            quality_score=float(quality_score),
            source=source,
            output_digest_sha256=self._digest(completion),
        )

    def format_qa(
        self,
        question: str,
        answer: str,
        domain: str,
        quality_score: float,
        source: str,
    ) -> TrainingRecord:
        return TrainingRecord(
            prompt=question.strip(),
            completion=answer.strip(),
            domain=domain,
            quality_score=float(quality_score),
            source=source,
            output_digest_sha256=self._digest(answer.strip()),
        )

    @staticmethod
    def to_jsonl(record: TrainingRecord) -> str:
        return json.dumps(
            {
                "prompt": record.prompt,
                "completion": record.completion,
                "domain": record.domain,
                "quality_score": record.quality_score,
                "source": record.source,
                "output_digest_sha256": record.output_digest_sha256,
            },
            ensure_ascii=False,
        )
