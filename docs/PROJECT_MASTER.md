# AI 온디바이스 플랫폼 — 프로젝트 마스터 문서

> 새 채팅창이 열릴 때마다 이 파일을 붙여넣으면 전체 맥락이 즉시 복원됩니다.
> 최종 업데이트: 2026-03-10 (PR #552 반영)

---

## 1. 프로젝트 정의

**목표:**
노트북, 데스크톱, 스마트폰, 태블릿 등 사용자 개인 기기에서 직접 실행되는
우리 소유의 로컬 AI 모델팩을 기반으로,
개인·팀·부서·전사 단위의 정책, 배포, 권한, 감사, 업데이트를
통합 관리할 수 있는 기업용 온디바이스 AI 플랫폼 구축.

**핵심 원칙:**
- 온디바이스 = 데스크톱/노트북/태블릿/스마트폰 공통 로컬 실행
- 로컬 우선, 오프라인 가능, 클라우드 fallback은 명시적 승인 시에만
- 모델은 로컬, 권한은 엔터프라이즈
- 알고리즘팀 산출물은 플랫폼에 즉시 반영 (별도 설계 없음)

---

## 2. 레포지토리

**Claude Code 실행:**
```bash
# 일반 실행 (기본값 — 권장)
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP" && claude

# 파일 시스템 전체 접근이 필요한 경우에만 (예외적 opt-in)
# cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP" && claude --dangerously-skip-permissions
```

---

## 3. 팀 구조

| 팀 | 역할 |
|---|---|
| 플랫폼 개발팀 | 검증/증빙/공급망/라우팅 인프라/품질 게이트 |
| 알고리즘 개발팀 | 모델팩 규격 + 라우팅 알고리즘 + fingerprint 설계 + 기업용 정책 |

**통합 원칙 (알고리즘팀 산출물 → 즉시 플랫폼 반영):**
- 모델팩 규격 → platform manifest
- 라우팅 알고리즘 → chooseBestPack()
- fingerprint 설계 → ExecModeResultV4/V5
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
| #533 | pr/p22-p1-hotfix-final-sealed | P22-P1 핫픽스 봉인 | 완료 |
| #534 | pr/p22-p2-platform | P22-P2 플랫폼 체계화 | 완료 |
| #535 | pr/p22-ai-p0 | P22-AI P0 본체 | 완료 |
| #536 | pr/p22-ai-provenance | P22-AI 증빙 고도화 | 완료 |
| #537 | pr/p23-p0a-hard-seal | P23-P0A 바닥판 하드 봉인 | 완료 |
| #538 | pr/p23-p0b-real-model-path | P23-P0B 실모델 제품 경로 | 완료 |
| #539 | pr/p23-p1-product-quality | P23-P1 제품성 강화 | 완료 |
| #540 | pr/p23-p2-approval-provenance | P23-P2 승인·증빙 제품화 | 완료 |
| #541 | pr/p24-r-research-lane | P24-R 연구 레인 | 완료 |
| #542 | pr/project-master-doc | PROJECT_MASTER.md 초안 | 완료 |
| #543 | pr/p23-p2b-p25-ent-p0-unified | 알고리즘 인터페이스 정합 + 기업용 확장 | 완료 |
| #544 | pr/project-master-update-1 | PROJECT_MASTER.md PR #543 반영 | 완료 |
| #545 | pr/p25-ent-h1-enterprise-contract-hotfix | power_class 'mid' 봉인 + 7개 기기 클래스 | 완료 |
| #546 | pr/p25-ent-h2-exec-mode-v4-strict | ExecModeResultV4 strict validation | 완료 |
| #547 | pr/ai-p3-04-policy-conflict-engine | 권한 escalation 차단 엔진 | 완료 |
| #548 | pr/ai-p3-03-enterprise-router-enforcement | 2단계 엔터프라이즈 라우터 | 완료 |
| #549 | pr/ai-p3-05-exec-fingerprint-canonical | ExecModeResultV5 + 실행 fingerprint 봉인 | 완료 |
| #550 | pr/ai-p3-06-device-probe-and-classify | 동적 기기 분류 (device probe) | 완료 |
| #551 | pr/no-raw-in-logs-exceptions-reports | NO_RAW_OUTPUT_POLICY_V1 전사 적용 | 완료 |
| #552 | pr/project-master-update-552 | 알고리즘팀 산출물 11개 + PROJECT_MASTER 갱신 | 완료 |

---

## 6. 현재 플랫폼 구현 상태

### 완료 ✅
- 검증기 체계 (exact parser, verifier chain, EXIT=0)
- JCS canonical + domain tag 전체 digest 통일
- 공급망 무결성 (bundle lock / Merkle tree / CycloneDX 1.6 / SPDX 2.3 / SLSA v1.2)
- TUF anti-rollback + freeze attack 방어
- 라우팅 V4 (하드 제약 + utility score)
- routing_decision_digest + routing_event_id 분리
- ExecModeResultV4 (pack identity 3분리 + 조직 컨텍스트)
- ExecModeResultV4 strict (SHA-256 형식 + rollout ring + routing 분리 검증)
- ExecModeResultV5 (ns/us 단위 고정 + ExecFingerprintMaterialV1 봉인)
- KvPolicy (baseline/shadow/active)
- Guided toolcall (schema-constrained)
- Tokenizer/chat_template lock (6개 digest + 필수화)
- Sustained perf gate 10분
- H2O KV cache (off-by-default, shadow)
- 양자화 전략 레지스트리 (AWQ/SmoothQuant/BitNet)
- HW-SW Pareto frontier
- runtime_manifest.json 구조 (micro/small)
- 기업용 조직 계층 (org/department/team/user 4단계)
- device_class_registry (7개 기기 클래스, PC/Mobile SLO 이원화)
- power_class 'mid' 봉인 ('medium' BLOCK)
- pack assignment policy (ring0~ring3, COMPUTED_AT_BUILD_TIME BLOCK)
- enterprise platform SSOT
- 권한 escalation 차단 엔진 (POLICY_CONFLICT_ENGINE_V1)
- 2단계 엔터프라이즈 라우터 (policy_digest/rollout_ring/device_class_id/offline_capable/target_groups)
- 동적 기기 분류 (device probe + classifyDeviceV1, probe-first + THERMAL_LIMITED)
- NO_RAW_OUTPUT_POLICY_V1 전사 적용 (safeLogDigestOnly, throwSafeError)
- 알고리즘팀 계약 파일 (model_pack_catalog, digest, tokenizer, eval_fingerprint_v2, device_probe_contract, runtime_variance_sampler)

### 대기 중 ⏳ (실 weights 투입 후)
- manifest status → verified
- smoke/eval fingerprint 실값
- SKIPPED verifier들 → ENFORCE=1 전환
- Butler 대시보드 Live 연결
- 전 기기군 실측 (RAM/latency/thermal)

---

## 7. 핵심 설계 결정 사항

| 결정 | 내용 |
|---|---|
| digest 표준 | JCS canonical JSON + domain tag (tools/crypto/digest_v1.ts) |
| routing 분리 | routing_decision_digest (timestamp 없음) vs routing_event_id (timestamp 포함) |
| manifest 구조 | 3층: logical_model_pack / compiled_runtime_pack / quality_contract |
| pack identity | logical + compiled + tokenizer_template 3분리 |
| 라우팅 원칙 | 엔터프라이즈 hard gate 우선 → 디바이스 hard gate → utility score |
| toolcall | unconstrained JSON 금지, schema-constrained 필수 |
| 양자화 | weight-only int4 기본 (W4A4 강제 금지) |
| KV cache | H2O off-by-default, shadow only |
| 기업 정책 | org → department → team → user 4단계 override, escalation BLOCK |
| 롤아웃 | ring0_canary → ring1_team → ring2_department → ring3_org |
| SLO 이원화 | PC: sustained_decode_tps / Mobile: thermal_degradation_pct |
| chat_template | chat 모델은 필수 (optional 금지) |
| ONNX external data | shard 허용 |
| power_class | 'low' / 'mid' / 'high' 만 허용 ('medium' BLOCK) |
| raw 출력 | 전 경로 금지, digest-only logging 강제 (NO_RAW_OUTPUT_POLICY_V1) |
| device 분류 | probe 실측값 기반 동적 분류, thermal_state=critical은 reason_code만 THERMAL_LIMITED |
| exec_fingerprint | timestamp/routing_event_id 제외, 8-field canonical material (ExecFingerprintMaterialV1) |

---

## 8. 모델팩 스펙

| 팩 | 기반 모델 | 양자화 | RAM | latency p95 | decode TPS 최소 | 상태 |
|---|---|---|---|---|---|---|
| micro_default | Qwen2.5-1.5B-Instruct | weight-only int4 | 1.5GB 이하 | 1200ms 이하 | 8 | pending_real_weights |
| small_default | Qwen2.5-3B-Instruct | weight-only int4 | 3.0GB 이하 | 2000ms 이하 | 8 | pending_real_weights |

**측정 계약:**
- prompt budget: 512 tokens / generation budget: 128 tokens
- search: do_sample=false, num_beams=1
- thermal_headroom >= 0.6, cold 1회 제외, warm runs 기준 p95
- sustained 10분 별도 측정

**필수 아티팩트 (팩당):**
`model.onnx`, `tokenizer.json`, `config.json`, `chat_template.jinja`, `runtime_manifest.json`, `SHA256SUMS`

**인도 일정 (T0 = 인터페이스 동결일):**
- micro_default 논리 모델: T0 + 2주 / verified: T0 + 4주
- small_default 논리 모델: T0 + 3~4주 / verified: T0 + 5~6주

---

## 9. 기기 클래스 정의

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

## 10. 알고리즘팀 산출물 계약 파일

| 파일 | 역할 |
|---|---|
| `tools/ai/model_pack_catalog_v1.ts` | 모델팩 빌드 스펙 (PackBuildSpecV1, SLO, 아티팩트 목록) |
| `tools/ai/model_pack_digest_v1.ts` | logical/tokenizer/pack identity digest 빌더 |
| `tools/ai/tokenizer_contract_v1.ts` | tokenizer 계약 (chat_template 필수, digest 검증) |
| `tools/ai/pack_artifact_contract_v1.ts` | 팩 아티팩트 존재 검증 (verifyPackArtifactsV1) |
| `tools/ai/eval_fingerprint_v2.ts` | EvalFingerprintV2 (schema_pass_rate ≥ 0.98, violation_rate ≤ 0.01) |
| `tools/ai/device_probe_contract_v1.ts` | 알고리즘팀 전용 기기 probe 계약 (probe_model_digest 포함) |
| `tools/ai/runtime_variance_sampler_v1.ts` | 런타임 분산 측정 (min 30샘플, p50/p95/p99) |
| `scripts/ai/build_micro_default_v1.py` | micro_default 팩 빌드 스크립트 |
| `scripts/ai/build_small_default_v1.py` | small_default 팩 빌드 스크립트 |
| `scripts/ai/run_smoke_eval_v1.py` | smoke eval (echo 탐지, digest-only 로깅) |
| `scripts/ai/measure_runtime_variance_v1.py` | 런타임 분산 측정 요약 (JSON 출력) |

---

## 11. PENDING 액션 아이템

1. 실 weights 파일 준비 (알고리즘팀)
   - T0 인터페이스 동결일 확정 필요
   - base checkpoint / reference device class / eval corpus 동결
2. 전 기기군 실측 (알고리즘팀)
3. PROJECT_MASTER.md PR 머지 후 최신 상태 유지

---

## 12. 전체 진행률

| 단계 | 내용 | 완성도 |
|---|---|---|
| P22 | 플랫폼 바닥판 | 100% |
| P23 | 제품화 + 증빙 | 100% |
| P24-R | 연구 레인 | 100% |
| P23-P2B | 알고리즘 인터페이스 정합 | 100% |
| P25-ENT-P0 | 기업용 플랫폼 확장 | 100% |
| P25-ENT-H1/H2 | 엔터프라이즈 계약 핫픽스 | 100% |
| AI-P3 | 알고리즘팀 통합 (라우터/fingerprint/probe/raw차단) | 100% |
| 알고리즘팀 산출물 계약 | 모델팩/tokenizer/eval/probe/variance | 100% |
| 실 weights | 모델 본선화 | 대기 중 |

**전체 서비스 목표 대비: 약 95%**

---

이 문서는 PR이 머지될 때마다 업데이트합니다.
