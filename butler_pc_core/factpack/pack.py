"""
Butler Fact Pack — Main pack class

JSON fact 파일들을 로드하고 매칭 인터페이스 제공.

사용 예:
    from butler_pc_core.factpack import FactPack

    pack = FactPack.from_default_facts_dir()
    match = pack.lookup("한국의 4대 보험은?")
    if match:
        print(match.fact.answer)
        print(f"출처: {match.fact.source} (검증일: {match.fact.verified_at})")
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from .matcher import Matcher
from .schema import Fact, FactMatch, FactPackFile

log = logging.getLogger(__name__)


class FactPack:
    """다수의 카테고리 fact JSON 파일들을 통합 관리."""

    PACK_VERSION = "1.0.0"

    def __init__(self, facts: List[Fact], threshold: float = Matcher.DEFAULT_THRESHOLD) -> None:
        self.facts = facts
        self.matcher = Matcher(facts, threshold=threshold)
        self._validate_no_expired()

    @classmethod
    def from_facts_dir(
        cls,
        facts_dir: Path,
        threshold: float = Matcher.DEFAULT_THRESHOLD,
        strict: bool = True,
    ) -> "FactPack":
        """디렉토리 내 모든 *.json 파일을 로드."""
        facts_dir = Path(facts_dir)
        if not facts_dir.is_dir():
            raise FileNotFoundError(f"facts 디렉토리를 찾을 수 없습니다: {facts_dir}")

        all_facts: List[Fact] = []
        loaded_files = 0
        seen_ids: set[str] = set()

        for json_path in sorted(facts_dir.glob("*.json")):
            try:
                with json_path.open("r", encoding="utf-8") as fp:
                    raw = json.load(fp)
                pack_file = FactPackFile.model_validate(raw)
            except Exception as e:
                msg = f"fact 파일 로딩 실패 [{json_path.name}]: {e}"
                if strict:
                    raise RuntimeError(msg) from e
                log.error(msg)
                continue

            # 전역 id 중복 검사
            for f in pack_file.facts:
                if f.id in seen_ids:
                    msg = f"전역 fact id 중복: {f.id} (파일: {json_path.name})"
                    if strict:
                        raise RuntimeError(msg)
                    log.error(msg)
                    continue
                seen_ids.add(f.id)
                all_facts.append(f)

            loaded_files += 1
            log.info(f"factpack 로드: {json_path.name} ({len(pack_file.facts)}개 fact)")

        if not all_facts:
            raise RuntimeError(f"facts 디렉토리에 유효한 fact가 없습니다: {facts_dir}")

        log.info(f"factpack 총 {len(all_facts)}개 fact 로드 ({loaded_files}개 파일)")
        return cls(facts=all_facts, threshold=threshold)

    @classmethod
    def from_default_facts_dir(cls, threshold: float = Matcher.DEFAULT_THRESHOLD) -> "FactPack":
        """패키지 기본 facts 디렉토리에서 로드."""
        default_dir = Path(__file__).parent / "facts"
        return cls.from_facts_dir(default_dir, threshold=threshold)

    def lookup(self, query: str) -> Optional[FactMatch]:
        """쿼리에 매칭되는 fact 반환. 미매칭 시 None."""
        return self.matcher.lookup(query)

    def stats(self) -> dict:
        """팩 상태 진단용."""
        cats = {}
        for f in self.facts:
            cats[f.category] = cats.get(f.category, 0) + 1
        return {
            "version": self.PACK_VERSION,
            "total_facts": len(self.facts),
            "categories": cats,
            "threshold": self.matcher.threshold,
        }

    def _validate_no_expired(self) -> None:
        """expires_at이 지난 fact가 있으면 경고."""
        today = date.today()
        expired = [f for f in self.facts if f.expires_at and f.expires_at < today]
        if expired:
            log.warning(
                f"만료된 fact {len(expired)}건 발견 (재검증 필요): "
                f"{[f.id for f in expired]}"
            )
