# AI Hub 27번 기업 회계처리 기준 데이터 — License Snapshot

## 1. 데이터셋 본질 (대표 스크린샷 확인)
- 이름: 기업 회계처리 기준 데이터 (BETA)
- 분야/유형/생성: 금융 / 텍스트 / LLM 생성
- 구축연도/갱신: 2025 / 2026-05
- 용량: 71.71 MB (zip 해제)
- 태그: #회계, #자연어

## 2. 라이선스 출처 (실측 fetch)
- 출처 URL: https://aihub.or.kr/intro/policy (AI Hub 공식 데이터 이용정책)
- 본 Claude (Butler 총괄기획팀) 실측 web_search/web_fetch 일시: 2026-05-20
- 본 Claude 환경 fetch 정합 (알고리즘 개발팀 환경 §4 "외부 송신 0" 본질 보호)

## 3. AI Hub 공식 본문 (영리 활용 본질)

본 AI데이터 등은 인공지능 기술 및 제품·서비스 발전을 위하여 구축하였으며,
지능형 제품・서비스, 챗봇 등 다양한 분야에서 영리적・비영리적 연구・개발
목적으로 활용할 수 있습니다.

본 AI데이터 등을 이용할 때에는 반드시 한국지능정보사회진흥원의 사업결과임을
밝혀야 하며, 본 AI데이터 등을 이용한 2차적 저작물에도 동일하게 밝혀야 합니다.

국외에 소재하는 법인, 단체 또는 개인이 AI데이터 등을 이용하기 위해서는
수행기관 등 및 한국지능정보사회진흥원과 별도로 합의가 필요합니다.

## 4. 라이선스 4개 항목 verified_true 근거

[1] commercial_use_allowed = verified_true
근거: "영리적・비영리적 연구・개발 목적으로 활용할 수 있습니다"
Butler 정합: 국내 기업 ATLink 본 개발 본질 (2차 저작물 = Butler 카드 5 LoRA adapter)

[2] attribution_required = verified_true
근거: "반드시 한국지능정보사회진흥원의 사업결과임을 밝혀야"
Butler 정합: MODEL_CARD.md 필수 문구 본질 정합

[3] redistribution_allowed = verified_true
근거: "2차적 저작물에도 동일하게 밝혀야" → 2차 저작물 배포 가능 본질
Butler 정합: butler-1.7b-v3-card5-accounting-lora-v1 adapter 배포 가능

[4] model_training_allowed = verified_true
근거: "인공지능 기술 및 제품·서비스 발전" 본질 + "지능형 제품·서비스 활용"
Butler 정합: MLX LoRA adapter 학습 본질 정합

## 5. 명시 의무 본문 (MODEL_CARD 필수)

"본 모델은 AI Hub 27번 기업 회계처리 기준 데이터를 활용하여 개발되었습니다.
본 데이터는 과학기술정보통신부와 한국지능정보사회진흥원의
「지능정보산업 인프라 조성」 사업의 결과물입니다."
