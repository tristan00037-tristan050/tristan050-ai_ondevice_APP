# Day 5 Progress

**날짜:** 2026-05-01  
**브랜치:** feature/day5-dmg-release-ux

## 완료 작업 목록

### 작업 1: Tauri --release 빌드

| 항목 | 결과 |
|------|------|
| Butler_0.1.0_aarch64.dmg | **3.0MB** (hdiutil UDZO 압축) |
| Butler.app | **7.9MB** |
| Rust 컴파일 | 45.51s (release profile, optimized) |
| 코드 서명 | 없음 (Apple Developer 미가입) |
| Gatekeeper 우회 | getting_started_v1.md 1.3절 안내 |

상세: `evidence/day5_release_build.md`

### 작업 2: 비개발자 UX 테스트

| 파일 | 내용 |
|------|------|
| `docs/beta/ux_test/scenario_v1.md` | 7개 시나리오 (41분 총 소요) |
| `docs/beta/ux_test/evaluation_form_v1.md` | 평가지 + 5명 집계표 |
| `docs/beta/ux_test/recruitment_v1.md` | 모집 가이드 + 일정 + 보상 |

대상: 비개발자 5명 (영업/마케팅/회계총무/기획/디자인)

### 작업 3: 베타 시작 가이드 v1

파일: `docs/beta/getting_started_v1.md`

| 섹션 | 내용 |
|------|------|
| 1. 설치 | .dmg 드래그 + Gatekeeper 우회 2가지 방법 |
| 2. 첫 실행 | 모델 로딩 + Personal Pack + Wi-Fi OFF 테스트 |
| 3. 카드 6개 | 각 카드 사용법 + 입력/출력 예시 |
| 4. 첨부 가이드 | 지원 형식 + S/M/L/XL 등급 |
| 5. Egress 검증 | 배지 위치 + Report 다운로드 + Wi-Fi OFF |
| 6. 진행률 + 중단 | 단계 표시 + 중단 시점 + 부분 결과 |
| 7. 알려진 한계 | known_limitations_v1.md 참조 |
| 8. 피드백 | GitHub Issues + 이메일 |

### 작업 4: 알려진 한계 페이지

파일: `docs/beta/known_limitations_v1.md`

| 영역 | 항목 수 |
|------|---------|
| 파일 처리 한계 | 6건 |
| 도메인 한계 | 6건 |
| 기술 한계 | 8건 |
| 언어 한계 | 5개 언어 |
| 모델 한계 | 8개 영역 |

### 작업 5: 샘플 테스트 자료 6세트

| 카드 | README | 입력 파일 |
|------|--------|-----------|
| card_01 요청 파악 | ✓ | input_email.txt (가상 이메일) |
| card_02 양식 변환 | ✓ | README만 (txt 파일 별도 추가 예정) |
| card_03 새 초안 | ✓ | input_past_doc.txt + input_new_situation.txt |
| card_04 문서 수정 | ✓ | README만 (txt 파일 별도 추가 예정) |
| card_05 회계 분류 | ✓ | input_bank.csv (가상 거래내역 30건) |
| card_06 양식 채우기 | ✓ | README만 (txt 파일 별도 추가 예정) |

## 누적 테스트 현황

| 유형 | 수 | 상태 |
|------|-----|------|
| Python 회귀 테스트 | 192 PASS | 8 기존 실패 (ONNX/AI 스텁) |
| Vitest (TS) | 24 PASS | 100% |
| 계 | **216+** | **Day 14 목표 85% 초과 유지** |

## Day 6 일정 및 위험

| 일정 | 내용 | 위험 |
|------|------|------|
| Day 6 오전 | T1(영업), T2(마케팅) UX 테스트 | 참여자 섭외 실패 시 일정 지연 |
| Day 6 오후 | T3(회계총무), T4(기획) UX 테스트 | — |
| Day 6 저녁 | T5(디자인) UX 테스트 | — |
| Day 6 완료 후 | 피드백 집계 → Day 7 반영 계획 수립 | 피드백 품질 낮을 경우 재테스트 |

**주요 위험 요인:**
- Apple 코드 서명 없음 → Gatekeeper 경고로 첫 실행 마찰 예상
- GGUF 모델 미포함 → 앱 실행 전 모델 별도 준비 필요
- butler_sidecar.py 별도 실행 필요 (향후 자동화 예정)
