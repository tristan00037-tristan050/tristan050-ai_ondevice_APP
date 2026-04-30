"""metadata_booster.py — 메타데이터 기반 스코어 보정."""
from __future__ import annotations

from datetime import datetime, timezone

from .chunkers import Chunk
from .rrf_fusion import RRFResult


def boost(
    results: list[RRFResult],
    factpack_ids: frozenset[str] | None = None,
    now: datetime | None = None,
    recency_days: int = 30,
    factpack_bonus: float = 0.05,
    recency_bonus: float = 0.03,
) -> list[RRFResult]:
    """RRF 결과에 메타데이터 보너스를 더해 재정렬한다.

    보너스 적용 우선순위:
    1. factpack_ids — 특정 문서가 "중요 팩"으로 지정된 경우 +factpack_bonus
    2. recency — chunk.metadata["modified_at"] ISO 8601 이 recency_days 이내면 +recency_bonus
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    boosted: list[tuple[float, RRFResult]] = []
    for r in results:
        extra = 0.0
        if factpack_ids and r.chunk.source_file in factpack_ids:
            extra += factpack_bonus
        modified_at_str = r.chunk.metadata.get("modified_at")
        if modified_at_str:
            try:
                modified = datetime.fromisoformat(modified_at_str)
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                age_days = (now - modified).total_seconds() / 86400
                if age_days <= recency_days:
                    extra += recency_bonus
            except ValueError:
                pass
        boosted.append((r.rrf_score + extra, r))

    boosted.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in boosted]
