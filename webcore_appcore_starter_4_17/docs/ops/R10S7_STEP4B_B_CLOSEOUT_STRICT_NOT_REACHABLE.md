# Step4-B B Closeout — Strict Improvement Not Reachable Under v0 (SSOT)

## SSOT 요약(숫자)
hit_stats_v0 (v0 기준):
- total_queries: 30
- first_hit_rank_is_1_queries: 24
- first_hit_rank_gt_1_queries: 2
- hitless_queries: 4

## 관측(사실)
- first_hit_rank_is_1_queries=24 이므로 해당 쿼리들은 first_hit 개선 여지가 없다.
- 개선 여지(첫 적중 랭크가 2 이상) 쿼리는 2개뿐이다.
- hitless_queries=4 이며, INTERNAL_K(candidate pull) 확장 적용 이후에도 Top-K 유입이 확인되지 않았다.

## 결론(운영 결정)
- Step4-B B(v0 게이트, 입력 고정) 조건에서 strict improvement ≥ 1 미달성 원인은 알고리즘 미작동이 아니라,
  "개선 여지(Headroom) 부족 + hitless 존재"로 SSOT에 의해 설명된다.
- Step4-B B는 안전성/정합/증빙을 봉인한 상태로 종료(CLOSED)하고,
  strict 개선 목표는 Step4-A 트랙으로 이관한다.

## 봉인된 구현(완료 항목)
- SSOT 정합: metrics(v0)와 동일 판정 기준으로 rank_stats/hit_stats_v0 경로 정합
- rank_stats SSOT (rank_changed, first_hit_rank_* 등)
- bm25_guard SSOT (total/sample)
- bucket_reordered 관련 SSOT
- INTERNAL_K(candidate pull) 도입 및 스윕

## Step4-A 이관 항목(범위)
- hitless(Top-K 밖) 해소를 위한 입력/필드 확장, 토큰화 확장, 평가/베이스라인 재앵커링
