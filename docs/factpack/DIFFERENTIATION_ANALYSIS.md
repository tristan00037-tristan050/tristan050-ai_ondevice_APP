# Butler Fact Pack — 글로벌 유사 서비스 차별화 분석

> 16 규칙 #14 — 우리 프로젝트와 유사하거나 동일한 전 세계 서비스를 자동으로 검색하고, 탐색하여, 전략적 차별화, 기술적 차별화, 서비스 차별화를 개발에 반영.

분석 기준일: 2026-05-02
분석 범위: 엔터프라이즈 사실 검증 / 환각 방지 / source-grounded AI 영역

---

## 1. 시장 맥락 (2026)

Stanford AI Index 2026에 따르면 26개 주요 LLM의 환각률이 **22% ~ 94%**에 이른다는 결과가 보고되었습니다. RAG(Retrieval-Augmented Generation)·tool grounding이 환각 감소에 가장 효과적인 아키텍처 결정으로 확인되었으며, 프롬프트 엔지니어링만으로는 5~15% 감소에 그친다는 것이 정설입니다.

이는 Butler가 추구하는 방향(검증된 사실의 결정론적 매칭 + LLM 폴백)이 업계 정설과 일치함을 의미합니다. 다만 **온디바이스 + 한국 도메인 + 결정론적 매처**라는 조합은 시장에 존재하지 않는 영역입니다.

---

## 2. 글로벌 유사 서비스 비교

| 서비스 | 본사 | 핵심 가치 | 배포 모델 | 한국 도메인 | 결정론적 매칭 | 응답 시간 (사실 Q&A) |
|---|---|---|---|---|---|---|
| **Glean** | 미국 | 엔터프라이즈 검색 + 컨텍스트 그라운딩 | 클라우드 SaaS | ✗ | ✗ (RAG, 확률적) | 수백 ms ~ 수 초 |
| **CustomGPT.ai** | 미국 | claim-level source verification, anti-hallucination | 클라우드 SaaS | ✗ | △ (소스 검증) | 1~3초 |
| **Knostic** | 미국 | AI grounding + access boundaries | 클라우드 SaaS | ✗ | ✗ | 수 초 |
| **Microsoft Copilot for M365 (with grounding)** | 미국 | Office 통합 + Graph 그라운딩 | 클라우드 (Azure) | △ (다국어) | ✗ | 수 초 |
| **Notion AI** | 미국 | 워크스페이스 내 검색·요약 | 클라우드 | △ | ✗ | 수 초 |
| **Kamiwaza AI (RIKER 평가)** | 미국 | 환각 측정 방법론 + 자체 모델 평가 | 평가 도구 | ✗ | ✗ | — |
| **Butler Fact Pack** | 한국 (ATLink) | **온디바이스 + 한국 사실 결정론 매칭 + LLM 폴백** | **온프레미스 (개인 PC)** | **✅ 한국 특화** | **✅ keywords gate + 유사도** | **0.5~2.3 ms** |

---

## 3. 차별화 — 3축 분석

### 3-1. 전략적 차별화 (왜 우리만의 영역인가)

**A. "데이터가 기기 밖으로 나가지 않음"** — 위 6개 경쟁자 모두 클라우드 의존
- 금융·의료·공공·국방 등 규제 산업은 클라우드 SaaS 도입이 사실상 불가
- Glean·CustomGPT 등은 SOC2/HIPAA 인증 보유하지만 "데이터 외부 전송 자체"가 금지된 영역에는 진입 못함
- Butler는 **물리적으로 차단된 환경에서도 동작** — 시장 자체가 다름

**B. 한국 도메인 사실 큐레이션** — 글로벌 서비스에 한국 4대보험·세율·최저임금 fact 큐레이션은 부재
- Microsoft Copilot/Glean은 다국어 지원하지만 "2026년 4대보험 요율 9.5%"같은 검증된 한국 사실 답변은 못함
- 일반 LLM이 한국 사실을 학습은 했지만 정확도 50% 수준 (결함 A 검증)
- Butler는 공식 출처 직접 확인된 50문항을 보유

**C. 베타 무료 → 회사 단위 도입 모델**
- Glean·CustomGPT는 좌석당 월 과금 (사용자당 $30~50)
- Butler는 회사 단위 라이선스 + 베타 무료 1개월 → 정식 도입
- 한국 중소·중견 기업은 좌석당 과금에 거부감 → 회사 단위 모델이 시장 적합

### 3-2. 기술적 차별화

**A. 결정론적 매칭 + LLM 폴백 하이브리드**
| 구분 | 일반 RAG | Butler Fact Pack |
|---|---|---|
| 사실 검증 매커니즘 | 임베딩 유사도 (확률적) | **keywords_required gate (결정론) + 유사도** |
| 출처 검증 | 검색된 문서를 LLM이 "참고"하여 생성 | **검증된 답변 그 자체를 직접 반환** (LLM 호출 없음) |
| 환각 위험 | LLM이 검색 결과를 왜곡할 위험 항상 존재 | **0% (LLM 거치지 않음)** |
| 응답 시간 | 임베딩 검색 + LLM 생성 = 수 초 | **0.5~2.3 ms** |

**B. 한국어 어절 변화 강건성**
- 글로벌 서비스는 영어 형태소 분석 기반 → 한국어 조사·어미 변화 ("4대보험은", "4대보험이", "4대보험을")에 약함
- Butler는 char 2-gram containment + light stemming으로 한국어 어절 변화 흡수
- KoNLPy 등 무거운 형태소 분석기 의존성 0 → 온디바이스 시작 시간 단축

**C. 의존성 최소화 (온디바이스 우선)**
- Glean: TypeScript 백엔드 + Elasticsearch + Embedding 모델
- Butler Fact Pack: **pydantic 단일 의존성** (~수 MB 메모리)
- 외부 라이브러리(rapidfuzz, KoNLPy 등) 0 — 온프레미스 배포 패키지 가벼움

### 3-3. 서비스 차별화

**A. 출처 자동 부착 + 검증일자 명시**
- 글로벌 서비스: "참고 문서 링크" 수준
- Butler: 답변 본문에 **공식 출처 + 검증일 + 유효기간** 푸터 자동 부착
  ```
  ─────────
  출처: 국민건강보험공단·국민연금공단·근로복지공단 공식 안내 (2026-05-01 기준)
  ※ 본 답변은 2026-12-31까지 유효 (이후 재검증 필요)
  ```

**B. 임계값 미달 시 명시적 폴백**
- 일부 경쟁자는 "확신 없음에도 답변" → 환각 발생
- Butler는 임계값 미달 시 LLM 폴백 + "AI 생성 응답" 배지 표기 → 사용자가 신뢰도 직접 판단

**C. 회사별 fact pack 확장 가능**
- 베타 1개월 후 회사별 자체 사실 추가 가능 (인사 정책, 회계 규정, 사내 절차 등)
- Glean은 가능하지만 클라우드 업로드 필수 → Butler는 온디바이스 보존
- 이것이 "쓰면 쓸수록 그 회사 자체가 되는 AI OS" 비전의 첫 구현

---

## 4. 경쟁 위협 분석

| 위협 | 가능성 | 시기 | 대응 |
|---|---|---|---|
| Glean의 한국어 강화 | 중 | 2027~ | 한국 도메인 사실 50→500문항 확장 + 회사별 확장 기능으로 선점 |
| Microsoft Copilot의 그라운딩 강화 | 높음 | 진행 중 | 온프레미스(클라우드 불가) 영역에 집중 |
| 한국 스타트업의 유사 시도 | 중 | 2026 하반기 | 베타 회사 5곳 → 30곳으로 lock-in 확보 |
| OpenAI/Anthropic의 도메인 fact 자체 학습 | 높음 | 2026 하반기 | LLM 자체 정확도가 올라가면 FactPack의 정확도 우위는 줄어듦. 단, **결정론·온디바이스·출처 표기·응답 속도** 차별화는 유효 |

---

## 5. 향후 개발 반영 항목

본 분석을 토대로 다음을 후속 PR에 반영할 예정입니다.

| 후속 PR | 반영 차별화 |
|---|---|
| #664 모델 sidecar 공유 | 응답 시간 우위 강화 (FactPack 미스 케이스 31s → 6s) |
| #665 디자인 개선 | 출처 배지 / 검증일 / 신뢰도 표시 UI 도입 — Glean·CustomGPT 시각적 메타포 참고하되 한국어·한국 기관 톤으로 |
| Fact Pack v2 (Day 15+) | 50 → 200문항 확장 + 회사별 fact pack 추가 기능 |
| 팀 서버 RAG (계층 2) | Glean식 엔터프라이즈 검색 차용하되 온프레미스로 |
| 중앙 서버 (계층 3) | Microsoft Graph식 통합 + 사내망 한정 |

---

## 6. 출처

본 분석은 다음 공개 자료를 직접 검색·확인하여 작성되었습니다.

- [Stanford AI Index 2026 — Engineering Strategies for High LLM Hallucination Rates](https://explore.n1n.ai/blog/stanford-ai-index-2026-hallucination-engineering-2026-04-21) (2026-04-21)
- [AI Hallucination Rate Benchmarks 2026: 5-Model Study](https://www.digitalapplied.com/blog/ai-model-hallucination-rate-benchmarks-2026-study) (2026-04, 5,000 prompt 벤치마크)
- [Best Source-Grounded AI Platforms in 2026](https://www.chitika.com/best-source-grounded-ai-platforms-in-2026-top-tools-compared/) (CustomGPT.ai 등 비교)
- [Glean — When LLMs Hallucinate in Enterprise Contexts](https://www.glean.com/perspectives/when-llms-hallucinate-in-enterprise-contexts-and-how-contextual-grounding) (2025-11-06)
- [Knostic — Solving the Very-Real Problem of AI Hallucination](https://www.knostic.ai/blog/ai-hallucinations) (2026-01-05)
- [Kamiwaza AI / arxiv RIKER 평가 (2026.03)](https://arxiv.org/pdf/2603.08274)
