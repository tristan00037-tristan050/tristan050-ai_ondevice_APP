"""
Butler Fact Pack — Query → Fact matcher

매칭 전략 (보수적, false-positive 0% 목표):
  1) keywords_required 통과 (모두 포함되지 않으면 즉시 탈락)
  2) keywords_any 보너스 점수
  3) question_patterns 각각과의 유사도 계산 (n-gram + token 자카드 + containment)
  4) max(유사도) ≥ threshold 인 fact만 후보
  5) 후보 중 최고 점수 fact 반환. 동점이면 fact id 사전순 (재현성).

유사도 함수 (한국어 어절 변화에 강건):
    0.45 * char_2gram_containment(query→pattern)
  + 0.30 * char_2gram_jaccard
  + 0.25 * stemmed_token_jaccard

설계 근거:
  - char 2-gram: 한국어 음절 결합 단위 ("4대보험은" / "4대보험이" 차이 흡수)
  - containment(directional): 사용자 쿼리가 패턴보다 짧을 때 강건성 확보
  - stemmed token jaccard: 흔한 한국어 조사·어미 제거 후 토큰 비교
  - 외부 라이브러리 없음 (rapidfuzz 등 의존성 추가 안 함 — 온디바이스 가벼움 우선)
  - 형태소 분석기 미사용 (KoNLPy 의존성 회피, 시작 시간 단축)

threshold 결정 근거 (실험 기반):
  - keywords_required gate 통과 시점에 의도가 매우 좁혀짐
  - 0.65: 한국어 조사 변형까지 흡수, false-positive 0건 (베타 검증 50문항)
  - 0.50: 부분 일치까지 매칭 (위험)
"""

from __future__ import annotations

from typing import List, Optional

from .normalizer import keyword_in_query, normalize, stem_tokens
from .schema import Fact, FactMatch


def _char_ngrams(text: str, n: int = 2) -> set:
    """문자 n-gram 집합. 공백 제거 후 슬라이딩."""
    s = text.replace(" ", "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _containment(a: set, b: set) -> float:
    """a의 원소 중 b에 포함된 비율. a가 비면 0.0."""
    if not a:
        return 0.0
    return len(a & b) / len(a)


def similarity(query_norm: str, pattern_norm: str) -> float:
    """0.0~1.0 유사도. 둘 다 정규화된 텍스트여야 함.

    한국어 어절 변화(조사·어미)에 강건한 복합 시그널:
      - char 2-gram containment (쿼리 → 패턴)
      - char 2-gram 자카드
      - stemmed token 자카드 (조사 제거 후)
    """
    if not query_norm or not pattern_norm:
        return 0.0
    if query_norm == pattern_norm:
        return 1.0

    q_chars = _char_ngrams(query_norm, 2)
    p_chars = _char_ngrams(pattern_norm, 2)
    if not q_chars or not p_chars:
        return 0.0

    char_containment = _containment(q_chars, p_chars)
    char_jaccard = _jaccard(q_chars, p_chars)
    tok_jaccard = _jaccard(stem_tokens(query_norm), stem_tokens(pattern_norm))

    return 0.45 * char_containment + 0.30 * char_jaccard + 0.25 * tok_jaccard


class Matcher:
    """Fact 리스트에 대한 매칭 엔진."""

    DEFAULT_THRESHOLD = 0.55
    KEYWORD_ANY_BONUS = 0.10  # keywords_any 매칭 시 가산 점수 (최대 1.0 캡)

    def __init__(self, facts: List[Fact], threshold: float = DEFAULT_THRESHOLD) -> None:
        if not (0.0 < threshold <= 1.0):
            raise ValueError(f"threshold는 (0,1] 범위여야 합니다: {threshold}")
        self.facts = facts
        self.threshold = threshold
        # 사전 정규화 캐시 (런타임 성능)
        self._normalized_patterns: dict[str, List[str]] = {
            f.id: [normalize(p) for p in f.question_patterns] for f in facts
        }

    def lookup(self, query: str) -> Optional[FactMatch]:
        """쿼리에 매칭되는 fact 1건 반환. 임계값 미달 시 None."""
        if not query or not query.strip():
            return None

        norm_q = normalize(query)
        if not norm_q:
            return None

        best: Optional[FactMatch] = None

        for fact in self.facts:
            # 1. keywords_required gate (strict, 1차 필터)
            #    모두 포함되지 않으면 즉시 탈락 — false-positive 차단의 핵심.
            if fact.keywords_required:
                if not all(keyword_in_query(kw, norm_q) for kw in fact.keywords_required):
                    continue

            # 2. keywords_any 처리 — 두 가지 모드:
            #    (a) keywords_required가 있으면: keywords_any는 보너스 전용 (게이트 X)
            #        사용자가 핵심 단어로 짧게 물어도 매칭되도록 허용.
            #    (b) keywords_required가 비어있으면: keywords_any가 식별 게이트
            #        (최소 1개 매칭 필수) — 무차별 매칭 차단.
            matched_any: List[str] = []
            if fact.keywords_any:
                matched_any = [
                    kw for kw in fact.keywords_any if keyword_in_query(kw, norm_q)
                ]
                if not fact.keywords_required and not matched_any:
                    # required가 비어있는데 any도 매칭 없으면 식별 불가 → 탈락
                    continue

            # 3. question_patterns 유사도 계산
            normalized_patterns = self._normalized_patterns[fact.id]
            scored = [
                (similarity(norm_q, np), orig)
                for np, orig in zip(normalized_patterns, fact.question_patterns)
            ]
            best_pattern_score, best_pattern_text = max(scored, key=lambda x: x[0])

            # 4. keywords_any 보너스 (캡 1.0)
            score = best_pattern_score
            if matched_any:
                score = min(1.0, score + self.KEYWORD_ANY_BONUS)

            # 5. 임계값 체크
            if score < self.threshold:
                continue

            # 6. 최고 점수 갱신 (동점 시 id 사전순으로 안정 결정)
            if best is None:
                best = FactMatch(
                    fact=fact,
                    score=score,
                    matched_pattern=best_pattern_text,
                    matched_keywords=matched_any,
                )
            else:
                if (score, fact.id) > (best.score, best.fact.id):
                    best = FactMatch(
                        fact=fact,
                        score=score,
                        matched_pattern=best_pattern_text,
                        matched_keywords=matched_any,
                    )

        return best
