# AI 온디바이스 플랫폼 — 프로젝트 마스터 문서

> 이 문서는 새 채팅창이 열릴 때마다 붙여넣으면 전체 맥락이 즉시 복원됩니다.
> 최종 업데이트: 2026-03

---

## 1. 프로젝트 정의

**목표:**
노트북, 데스크톱, 스마트폰, 태블릿 등 사용자 개인 기기에서 직접 실행되는
우리 소유의 로컬 AI 모델팩을 기반으로,
개인·팀·부서·전사 단위의 정책, 배포, 권한, 감사, 업데이트를
통합 관리할 수 있는 **기업용 온디바이스 AI 플랫폼** 구축.

**핵심 원칙:**
- 온디바이스 = 스마트폰 전용이 아닌, 데스크톱/노트북/태블릿/스마트폰 공통 로컬 실행
- 로컬 우선, 오프라인 가능, 클라우드 fallback은 명시적 승인 시에만
- 모델은 로컬, 권한은 엔터프라이즈

---

## 2. 레포지토리

GitHub: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP
로컬: /Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP

Claude Code 실행:
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP" && claude --dangerously-skip-permissions

---

## 3. 팀 구조

| 팀 | 역할 |
|---|---|
| 플랫폼 개발팀 | 검증/증빙/공급망/라우팅 인프라/품질 게이트 |
| 알고리즘 개발팀 | 모델팩 규격 + 라우팅 알고리즘 + fingerprint 설계 + 기업용 정책 |

통합 원칙:
알고리즘 개발팀 산출물은 아래 4곳에 즉시 반영:
- 모델팩 규격 → platform manifest
- 라우팅 알고리즘 → chooseBestPack()
- fingerprint 설계 → ExecModeResultV4
- 기업용 정책 → RouteContext / SSOT

---

## 4. 확정 워크플로우

1. 내가 최종안 전달 (또는 알고리즘팀 산출물)
2. Claude(여기)가 Claude Code 지시문 구성
3. Claude Code가 개발 실행 + PR 브랜치 생성
4. Claude(여기)가 PR 정보 구성 (main/compare/타이틀/본문)
5. 내가 GitHub에서 PR 머지

---

## 5. 완료된 PR 목록

| PR | 브랜치 | 내용 | 상태 |
|---|---|---|---|
| #533 | pr/p22-p1-hotfix-final-sealed | P22-P1 핫픽스 최종 봉인 | 완료 |
| #534 | pr/p22-p2-platform | P22-P2 플랫폼 체계화 | 완료 |
| #535 | pr/p22-ai-p0 | P22-AI P0 본체 | 완료 |
| #536 | pr/p22-ai-provenance | P22-AI 증빙 고도화 | 완료 |
| #537 | pr/p23-p0a-hard-seal | P23-P0A 바닥판 하드 봉인 | 완료 |
| #538 | pr/p23-p0b-real-model-path | P23-P0B 실모델 제품 경로 | 완료 |
| #539 | pr/p23-p1-product-quality | P23-P1 제품성 강화 | 완료 |
| #540 | pr/p23-p2-approval-provenance | P23-P2 승인·증빙 제품화 | 완료 |
| #541 | pr/p24-r-research-lane | P24-R 연구 레인 | 완료 |

---

## 6. 진행 중인 PR

| PR | 브랜치 | 내용 | 상태 |
|---|---|---|---|
| 예정 | pr/p23-p2b-p25-ent-p0-unified | 알고리즘팀 인터페이스 정합 + 기업용 확장 | 진행 중 |

---

## 7. 현재 플랫폼 구현 상태

### 완료
- 검증기 체계 (exact parser, verifier chain, EXIT=0)
- RFC 8785 JCS canonical + domain tag 전체 digest 통일
- 공급망 무결성 (bundle lock / Merkle tree / CycloneDX 1.6 / SPDX 2.3 / SLSA v1.2)
- 라우팅 V4 (하드 제약 + utility score, thermal/battery/latency/RAM)
- routing_decision_digest + routing_event_id 분리
- ExecModeResultV3 5중 추적
- TUF anti-rollback + freeze attack 방어
- Guided toolcall (schema-constrained)
- Tokenizer/chat_template lock (6개 digest)
- Sustained perf gate 10분
- H2O KV cache (off-by-default, shadow)
- 양자화 전략 레지스트리 (AWQ/SmoothQuant/BitNet)
- HW-SW Pareto frontier

### 진행 중
- runtime_manifest.json (알고리즘팀 요청)
- chat_template 필수화
- PackCandidate V2 (compiled/tokenizer/delegate 추가)
- ExecModeResultV4 (조직 컨텍스트 포함)
- 기업용 조직 계층 (org/department/team/user)
- device_class_registry (7개 기기 클래스)
- Pack assignment policy (ring0~ring3)

### 대기 중 (실 weights 투입 후)
- manifest status → verified
- smoke/eval fingerprint 실값
- SKIPPED verifier들 → ENFORCE=1 전환
- Butler 대시보드 Live 연결

---

## 8. 핵심 설계 결정 사항

| 결정 | 내용 |
|---|---|
| digest 표준 | RFC 8785 JCS canonical JSON + domain tag |
| routing 분리 | routing_decision_digest (timestamp 없음) vs routing_event_id (timestamp 포함) |
| manifest 구조 | 3층: logical_model_pack / compiled_runtime_pack / quality_contract |
| 라우팅 원칙 | 하드 제약 우선, utility score 후순위 |
| toolcall | unconstrained JSON 금지, schema-constrained 필수 |
| 양자화 | weight-only int4 기본 (W4A4 강제 금지) |
| KV cache | H2O off-by-default, shadow only |
| 기업 정책 | org → department → team → user 4단계 override |
| 롤아웃 | ring0_canary → ring1_team → ring2_department → ring3_org |
| SLO 이원화 | PC: sustained_decode_tps / Mobile: thermal_degradation_pct |

---

## 9. 모델팩 스펙

| 팩 | 양자화 | RAM | latency p95 | 상태 |
|---|---|---|---|---|
| micro_default | weight-only int4 | 1.5GB 이하 | 1200ms 이하 | pending_real_weights |
| small_default | weight-only int4 | 3.0GB 이하 | 2000ms 이하 | pending_real_weights |

측정 계약:
- prompt budget: 512 tokens
- generation budget: 128 tokens
- search: do_sample=false, num_beams=1
- thermal_headroom >= 0.6
- cold 1회 제외, warm runs 기준 p95

인도 일정 (T0 = 인터페이스 동결일):
- micro_default 논리 모델: T0 + 2주
- micro_default verified: T0 + 4주
- small_default 논리 모델: T0 + 3~4주
- small_default verified: T0 + 5~6주

---

## 10. 기기 클래스 정의

| device_class_id | 설명 | backend | SLO 기준 |
|---|---|---|---|
| desktop_gpu | 데스크톱 GPU | cuda | sustained_decode_tps 30 이상 |
| desktop_cpu | 데스크톱 CPU | cpu | sustained_decode_tps 10 이상 |
| laptop_gpu | 노트북 GPU | cuda | sustained_decode_tps 20 이상 |
| laptop_cpu | 노트북 CPU | cpu | sustained_decode_tps 8 이상 |
| phone_npu | 스마트폰 NPU | nnapi | thermal_degradation 20% 이하 |
| tablet_npu | 태블릿 NPU | nnapi | thermal_degradation 15% 이하 |
| tablet_gpu | 태블릿 GPU | metal | thermal_degradation 15% 이하 |

---

## 11. PENDING 액션 아이템

1. pr/p23-p2b-p25-ent-p0-unified PR 머지
2. 실 weights 파일 준비 (알고리즘팀)
   - T0 = 인터페이스 동결일 확정 필요
   - base checkpoint / reference device class / eval corpus 동결
3. 전 기기군 실측 (알고리즘팀)
4. 기업용 조직 계층 정책 엔진 완성

---

## 12. 전체 진행률

| 단계 | 내용 | 완성도 |
|---|---|---|
| P22 | 플랫폼 바닥판 | 100% |
| P23 | 제품화 + 증빙 | 100% |
| P24-R | 연구 레인 | 100% |
| P23-P2B | 알고리즘 인터페이스 정합 | 진행 중 |
| P25-ENT | 기업용 확장 | 진행 중 |
| 실 weights | 모델 본선화 | 대기 중 |

전체 서비스 목표 대비: 약 85%

---

이 문서는 PR이 머지될 때마다 업데이트합니다.
