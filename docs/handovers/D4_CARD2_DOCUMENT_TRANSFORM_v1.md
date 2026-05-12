# D-4 카드 2 본 기능 인계서 — 남의 문서 → 우리 양식

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0 |
| 작성일 | 2026-05-11 |
| 작성자 | 주식회사 에이티링크 / Butler AI |
| 인계 대상 | Claude Code (D-4 본 기능 개발) |
| 사이클 추정 | 3~5일 |
| 카드 식별 | 2 / 8 (베타 1차) — 요청 파악(D-3) 다음 카드 |
| 아이콘 | `<ArrowRightLeft />` (Lucide — 이모지 X) |
| 결함 추격 목표 | **30% 이하** (D-3 실측 67%에서 절반 감소) |

---

## §1 사이클 개요

### 1.1 D-2/D-3 학습 사항 통합

D-2 회계 분류(12개 PR, 91.7% 결함 추격) + D-3 요청 파악(7개 PR, 67% 결함 추격)에서 도출된 **핵심 반복 결함 패턴**이 본 인계서 §8에 체크리스트로 완전 통합되었습니다. D-4에서 30% 이하 달성 여부가 베타 1차 전체 품질의 분기점입니다.

| D-2/D-3 반복 결함 | D-4 적용 |
|---|---|
| 카드 타일 `active: false` 상태로 개발 시작 | §8.1 — 첫 커밋에서 `active: true` 의무 |
| 모달 오버레이가 메인 화면을 덮거나 파괴 | §8.2 — `position: fixed` 오버레이 + 메인 화면 보존 패턴 명세 |
| textarea 높이 부족, 버튼 비일관성 | §8.3 — UX 치수 사전 고정 |
| 이모지 헤더 → Lucide 교체 핫픽스 반복 | §8.4 — 개발 시작 시점부터 Lucide 아이콘 의무 |
| Spinner CSS → Loader2 재작업 | §8.5 — Loader2 + 진행 바 패턴 사전 명세 |
| 결과 영역 분리 미흡 (한 덩어리) | §8.6 — 섹션별 시각 구분 명세 |
| Load failed TypeError (sidecar 미준비) | §8.7 — wall-clock 60s 폴링 첫 커밋 의무 |
| python-docx / pdfminer 의존성 누락 | §8.8 — 의존성 파일 체크리스트 의무 |
| GUI 검증 마지막에 몰아서 → 대규모 수정 | §8.9 — PR별 GUI 검증 의무 |

### 1.2 베타 1차 카드 진행 상태

| # | 아이콘 | 카드 | D-Day | 상태 |
|---|---|---|---|---|
| 1 | 📥 | 요청 핵심 파악·정리 | D-3 | ✅ 완료 (PR #694~#698) |
| 2 | ArrowRightLeft | **남의 문서 → 우리 양식** | **D-4** | **★ 본 인계서** |
| 3 | 📄 | 기존 문서 기반 새 초안 | D-5 | 대기 |
| 4 | 📝 | 첨부 문서 수정·보완 | D-6 | 대기 |
| 5 | Calculator | 통장·거래내역 → 회계 분류 | D-2 | ✅ 완료 |
| 6 | 📋 | 상대 양식에 우리 자료 채우기 | D-7 | 대기 |
| 7 | 🎙️ | 회의 음성 → 회의록 | D-8 | 대기 |
| 8 | 📊 | 데이터 → 인사이트 | D-9 | 대기 |

### 1.3 D-4 단일 PR 전략 (D-3 분할 전략 폐기)

D-3는 3개 PR 분리 계획으로 시작했으나 실제 7개 PR이 소요되었습니다. D-4는 **본 기능 + 의존성 + UI 통합을 단일 PR로** 진행합니다.

| D-3 방식 (폐기) | D-4 방식 (채택) |
|---|---|
| PR #A: 본 기능 | **PR #하나**: 백엔드 + UI + 다운로드 통합 |
| PR #B: UX 보강 | (핫픽스 발생 시에만 PR #추가) |
| PR #C: 다운로드 | |
| + 핫픽스 4개 | |

---

## §2 카드 식별 + 본 기능 정의

### 2.1 카드 메타데이터

| 항목 | 내용 |
|---|---|
| 카드 ID | 2 |
| Lucide 아이콘 | `ArrowRightLeft` (size=24, already imported in EmptyState.tsx) |
| 카드명 | 남의 문서 → 우리 양식 |
| EmptyState mode | `format_convert` |
| App.tsx CARD_MODE_MAP | `2: 'format_convert'` (이미 등록됨) |
| 현재 `active` | `false` → **첫 커밋에서 `true`로 변경 필수** |
| 설명 문구 | 외부 문서 + 우리 과거 양식 |

### 2.2 본 기능 정의

```
입력 1 (외부 문서):  남의 문서 — .docx / .pdf / .eml / .txt / .md
입력 2 (우리 양식):  우리 과거 양식 — .docx / .md

처리:
  ① 외부 문서 핵심 내용 추출
  ② 우리 양식 구조 분석 (섹션 / 표 / 목록 / 어조)
  ③ LLM: 외부 내용 → 우리 양식 구조에 매핑
  ④ 우리 양식 형식으로 새 문서 생성

출력:  우리 양식 형식으로 변환된 새 문서 — .docx / .md
```

### 2.3 D-3와의 본질적 차이

| 영역 | D-3 (요청 파악) | D-4 (문서 변환) |
|---|---|---|
| 입력 수 | 1개 (외부 텍스트) | **2개** (외부 문서 + 우리 양식) |
| 핵심 처리 | 자연어 → 구조화 JSON | **두 문서 매핑 + 스타일 보존** |
| 출력 형식 | JSON → 화면 표시 | **새 문서 파일** (.docx / .md) |
| LLM 작업 | 추출 + 분류 | **내용 이해 + 형식 적용** |
| 성공 기준 | 5초 인지 | **우리 양식처럼 보임** |

---

## §3 사용자 페르소나 + 7단계 시나리오

### 3.1 페르소나 — 한국 중소기업 실무자

| 영역 | 페르소나 |
|---|---|
| 직책 | 과장 / 차장 / 팀장 (문서 작성 실무자) |
| 부서 | 영업, 기획, 경영지원, 마케팅 |
| 사용 시점 | 거래처/파트너가 보낸 문서를 우리 양식으로 다시 만들어야 할 때 |
| 주요 고민 | "이 거래처 제안서를 우리 회사 양식으로 정리해야 하는데…" |
| 한국 특수성 | 공문 형식 (수신/제목/내용), 한국식 표 구조, 한국어 어조 보존 |

### 3.2 7단계 시나리오 — 영업팀 박 과장 사례

```
[Step 1] 박 과장이 거래처로부터 제안서 수신
   - 거래처 제안서 (A사 양식, 20페이지 PDF)
   - 우리 회사 제안서 양식 (과거 작성본 .docx) 보유

[Step 2] Butler 카드 2 (ArrowRightLeft 남의 문서 → 우리 양식) 클릭

[Step 3] 두 파일 업로드
   ┌─ 외부 문서 ─────────────────────────────────────────┐
   │  📄 A사_제안서_2026Q2.pdf  [변경]                  │
   └────────────────────────────────────────────────────┘
   ┌─ 우리 양식 ─────────────────────────────────────────┐
   │  📄 우리회사_제안서양식_2025.docx  [변경]           │
   └────────────────────────────────────────────────────┘
   
   [선택] 변환 옵션:
   ☑ 우리 회사 헤더/푸터 유지
   ☑ 날짜·작성자 자동 채우기
   ☐ 원본 출처 각주 추가

[Step 4] SSE phase 4단계 진행 (실시간 표시)
   phase[0] "외부 문서 분석 중..."   (텍스트 추출 + 섹션 파악)
   phase[1] "우리 양식 구조 분석 중..."  (헤더/섹션/표 구조 파악)
   phase[2] "내용 매핑 중..."         (LLM: 외부 내용 → 우리 양식 구조)
   phase[3] "문서 생성 중..."         (python-docx 렌더링)

[Step 5] 결과 미리보기 화면
   ┌──────────────────────────────────────────────────────────┐
   │ ArrowRightLeft 남의 문서 → 우리 양식 — 변환 결과        │
   ├──────────────────────────────────────────────────────────┤
   │ 📊 변환 신뢰도: 88% (높음)                               │
   │                                                          │
   │ ✅ 매핑 완료 섹션: 5 / 6                                 │
   │ ⚠️  미매핑 섹션: 1개 (원본에 없는 "예산 세부" 섹션)     │
   │                                                          │
   │ ── 변환 결과 미리보기 ──                                 │
   │ [제목] 2026년 2분기 솔루션 제안서                        │
   │ [배경] A사가 제안한 클라우드 전환 배경: ...              │
   │ [제안 내용] ...                                          │
   │ [기대 효과] ...                                          │
   │ [예산] ...                                               │
   │ [일정] ...                                               │
   │ ⚠️  [예산 세부] → (원본 미포함, 빈 섹션으로 처리됨)     │
   │                                                          │
   │ [📥 .docx 다운로드] [📋 .md 다운로드] [👍 적합] [👎 부적합] │
   └──────────────────────────────────────────────────────────┘

[Step 6] .docx 다운로드 (우리 양식 형식의 새 문서)

[Step 7] (선택) 피드백
   - 👍 "적합함" → 학습 데이터 저장
   - 👎 "부적합" → 어느 섹션이 맞지 않는지 표시
```

### 3.3 입력 형식별 처리

| 파일 | 처리 라이브러리 |
|---|---|
| .docx (외부/양식) | python-docx — 단락·표·스타일 추출 |
| .pdf (외부 문서) | pdfminer.six — 텍스트 + 구조 추출 |
| .txt (외부) | 직접 텍스트, 섹션 휴리스틱 (빈 줄 기준) |
| .md (외부/양식) | 마크다운 파싱 (# 레벨로 섹션 구분) |
| .eml (외부) | email 모듈 — 본문 추출 후 처리 |

**양식 파일 제약**: .docx 또는 .md만 허용 (구조 파악 가능한 형식). .pdf는 양식으로 사용 불가 (쓰기 불가 형식임).

---

## §4 처리 흐름 (백엔드 상세)

### 4.1 전체 파이프라인

```
외부 문서                 우리 양식
    │                         │
    ▼                         ▼
[텍스트 추출]          [구조 분석]
    │                    (섹션 목록)
    │                         │
    └──────────┬──────────────┘
               ▼
         [LLM 매핑 프롬프트]
         "외부 문서의 내용을
          우리 양식의 각 섹션에
          맞게 재작성하세요"
               │
               ▼
         [매핑 결과 JSON]
         {sections: [{heading, content}]}
               │
               ▼
         [python-docx 렌더링]
         (우리 양식 스타일 적용)
               │
               ▼
           output.docx
```

### 4.2 양식 구조 분석 (TemplateParser)

```python
# butler_pc_core/document_transform/template_parser.py

@dataclass
class TemplateSection:
    heading: str          # "배경", "제안 내용", "예산" 등
    level: int            # 1=h1, 2=h2, 3=h3
    placeholder_text: str # 기존 내용 (매핑 힌트)
    format_hint: str      # "paragraph" | "table" | "bullet_list"
    is_required: bool     # 필수 섹션 여부 (비어 있으면 ⚠️ 표시)

def parse_docx_template(path: Path) -> List[TemplateSection]:
    """
    .docx 양식에서 섹션 구조 추출.
    - Heading 1/2/3 스타일 → 섹션 분리
    - 표(Table) → format_hint = "table"
    - 목록(List) → format_hint = "bullet_list"
    - 일반 단락 → format_hint = "paragraph"
    """
    ...

def parse_md_template(path: Path) -> List[TemplateSection]:
    """
    .md 양식에서 섹션 구조 추출.
    # → level 1, ## → level 2, ### → level 3
    """
    ...
```

### 4.3 출력 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DocumentTransformResult",
  "type": "object",
  "required": ["sections", "confidence", "unmapped_sections"],
  "properties": {
    "sections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["heading", "level", "content", "format", "mapped"],
        "properties": {
          "heading":  {"type": "string"},
          "level":    {"type": "integer", "minimum": 1, "maximum": 3},
          "content":  {"type": "string"},
          "format":   {"type": "string", "enum": ["paragraph", "table", "bullet_list"]},
          "mapped":   {"type": "boolean", "description": "외부 문서에서 매핑 성공 여부"},
          "source_excerpt": {"type": "string", "description": "외부 문서 참조 원문 (최대 200자)"}
        }
      }
    },
    "unmapped_sections": {
      "type": "array",
      "items": {"type": "string"},
      "description": "외부 문서에서 해당 내용을 찾지 못한 섹션 heading 목록"
    },
    "confidence": {
      "type": "number", "minimum": 0, "maximum": 1
    },
    "external_doc_title": {"type": "string"},
    "template_section_count": {"type": "integer"},
    "mapped_section_count": {"type": "integer"}
  }
}
```

### 4.4 LLM 프롬프트 설계

```python
TRANSFORM_PROMPT = """
당신은 한국 중소기업의 문서 변환 전문가입니다.

[외부 문서 내용]
{external_content}

[우리 양식 섹션 목록]
{template_sections_json}

[지시사항]
1. 외부 문서의 내용을 우리 양식의 각 섹션에 맞게 재작성하세요.
2. 각 섹션의 format_hint에 맞는 형식으로 출력하세요:
   - "paragraph": 서술형 문장
   - "table": 마크다운 표 형식 (| 컬럼 | 값 |)
   - "bullet_list": - 항목1 / - 항목2 형식
3. 외부 문서에 해당 내용이 없으면 "mapped": false로 표시하세요.
4. 내용을 추가로 창작하지 마세요 — 외부 문서에 있는 내용만 사용하세요.
5. 한국어 비즈니스 어조를 유지하세요 (존댓말, 공문 형식 등).

[응답 형식]
아래 JSON Schema에 맞게 응답하세요:
{schema}
"""
```

### 4.5 한국 비즈니스 문서 특수 처리

| 특수 상황 | 처리 방법 |
|---|---|
| 공문 형식 (수신/발신/제목) | TemplateSection에서 공문 헤더 자동 감지 → 날짜/작성자 자동 채우기 |
| 표 구조 보존 | 외부 문서 표 → 내용 추출 후 우리 양식 표 구조에 재배치 |
| 조직도/흐름도 | 텍스트 설명으로 대체 + "원본 참조 요망" 주석 추가 |
| 영문 외래어 혼용 | 원본 그대로 보존 (번역하지 않음) |
| 금액 표현 | 쉼표 포함 한국식 (1,000,000원) 그대로 보존 |

### 4.6 미매핑 + 저신뢰도 처리

| 신뢰도 | UI 처리 |
|---|---|
| 90% 이상 | 정상 결과 + 👍/👎 버튼 |
| 70~90% | "확인 필요" 배너 + 미매핑 섹션 ⚠️ 표시 |
| 50~70% | 경고 강조 + "일부 섹션을 변환하지 못했습니다" |
| 50% 미만 | 부분 결과 + "변환에 어려움이 있었습니다. 수동 보완이 필요합니다" |

미매핑 섹션 처리:
- UI에서 `⚠️ [섹션명] → (원본 미포함, 빈 섹션으로 처리됨)` 표시
- .docx 출력에서 해당 섹션 제목은 유지, 본문에 `[내용 없음]` 플레이스홀더

---

## §5 GUI 요건

### 5.1 와이어프레임 — 초기 화면 (두 파일 업로드)

```
┌──────────────────────────────────────────────────────────────────┐
│  ArrowRightLeft 남의 문서 → 우리 양식                    ❌       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  외부 문서를 우리 회사 양식으로 변환합니다.                       │
│                                                                  │
│  ── 1. 외부 문서 (남의 문서) ──────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  📄 파일을 여기에 드래그하거나 클릭하여 업로드하세요       │  │
│  │  .docx / .pdf / .eml / .txt / .md                         │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ── 2. 우리 양식 (과거 작성본) ────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  📄 파일을 여기에 드래그하거나 클릭하여 업로드하세요       │  │
│  │  .docx / .md                                               │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [변환 옵션 ▼]                                                    │
│  ☑ 우리 회사 헤더/푸터 유지   ☑ 날짜·작성자 자동 채우기         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                ▶ 변환하기                                │    │
│  └──────────────────────────────────────────────────────────┘    │
│  (두 파일 모두 업로드 전: 비활성 — disabled 스타일)               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 와이어프레임 — 파일 업로드 완료 상태

```
│  ── 1. 외부 문서 ──────────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ✅ A사_제안서_2026Q2.pdf  (342 KB)              [변경]     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ── 2. 우리 양식 ──────────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ✅ 우리회사_제안서양식_2025.docx  (88 KB)       [변경]     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                ▶ 변환하기  (primary, 풀폭)               │    │
│  └──────────────────────────────────────────────────────────┘    │
```

### 5.3 와이어프레임 — 변환 진행 중 (Loader2 + 4단계)

```
│                      ⟳  (Loader2, size=64, animate-spin)        │
│                                                                  │
│                   변환 중...                                      │
│                   단계 2 / 4                                      │
│                                                                  │
│  ①──────────────②──────────────③──────────────④                 │
│  ✓               2               ○               ○               │
│  (완료)        (현재)          (대기)           (대기)           │
│                                                                  │
│  ████████████████████░░░░░░░░░░░░░░░░░░   50%                   │
│                                                                  │
│  ┌────────┐                                                       │
│  │  취소  │  (border: 1.5px solid #d1d5db)                       │
│  └────────┘                                                       │
```

### 5.4 와이어프레임 — 변환 결과

```
│  ArrowRightLeft 남의 문서 → 우리 양식 — 변환 결과                 │
│  ──────────────────────────────────────                          │
│  📊 변환 신뢰도: 88%   ✅ 매핑 완료: 5/6   ⚠️ 미매핑: 1         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  [제목] 2026년 2분기 솔루션 제안서                      │     │
│  ├─────────────────────────────────────────────────────────┤     │
│  │  [배경] ...변환된 내용...                               │     │
│  ├─────────────────────────────────────────────────────────┤     │
│  │  [제안 내용] ...변환된 내용...                          │     │
│  ├─────────────────────────────────────────────────────────┤     │
│  │  ⚠️ [예산 세부] 원본 미포함 — 빈 섹션으로 처리됨       │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  [📥 .docx 다운로드] [📋 .md 다운로드] [👍 적합] [👎 부적합]     │
```

---

## §6 자동 검증 요건

### 6.1 pytest (신규 +8)

| 테스트 | 통과 기준 |
|---|---|
| `test_template_parser_docx_sections` | .docx 양식에서 섹션 목록 정확 추출 |
| `test_template_parser_md_sections` | .md 양식에서 #레벨 섹션 정확 추출 |
| `test_external_doc_text_extraction_docx` | .docx 외부 문서 텍스트 추출 완료 |
| `test_external_doc_text_extraction_pdf` | .pdf 외부 문서 텍스트 추출 완료 |
| `test_transform_result_schema_valid` | 변환 결과 JSON Schema 준수 |
| `test_unmapped_section_marked_correctly` | 미매핑 섹션 `mapped: false` 정확 표시 |
| `test_confidence_threshold_routing` | 신뢰도 50/70/90 임계값별 올바른 분기 |
| `test_transform_stream_phase_sequence` | SSE phase 0→1→2→3→complete 순서 |

### 6.2 Vitest (신규 +5)

| 테스트 | 통과 기준 |
|---|---|
| `test_card2_active_true_not_disabled` | 카드 2가 클릭 가능 상태 (`active: true`) |
| `test_document_transform_modal_opens_on_card2_click` | 카드 2 클릭 → DocumentTransformModal 오픈 |
| `test_transform_button_disabled_until_both_files` | 두 파일 업로드 전 "변환하기" 비활성 |
| `test_loading_spinner_loader2_animate_spin` | 진행 중 Loader2 `animate-spin` class 확인 |
| `test_result_shows_mapped_and_unmapped_sections` | 결과 화면에 매핑 완료 + 미매핑 섹션 모두 표시 |

### 6.3 TypeScript + 빌드

| 검증 | 기준 |
|---|---|
| `npx tsc --noEmit` | 오류 없음 |
| `npm run tauri build` | .app + .dmg 생성 (EXIT:0) |

---

## §7 결과 화면 영역

### 7.1 결과 .docx 구조

```
[문서 헤더 — 우리 양식 헤더/푸터 그대로]
날짜: 2026-05-11
작성: Butler AI (원본: A사_제안서_2026Q2.pdf 기반)

[섹션 1] 제목
2026년 2분기 솔루션 제안서

[섹션 2] 배경
...변환된 내용...

[섹션 3] 제안 내용
...변환된 내용...

[섹션 4] 기대 효과
...변환된 내용...

[섹션 5] 예산
...변환된 내용...

[섹션 6] 예산 세부
[내용 없음 — 원본 문서에 해당 내용이 포함되지 않았습니다]

[부록] 원본 출처
A사_제안서_2026Q2.pdf
변환 신뢰도: 88% | 매핑 완료: 5/6
```

### 7.2 결과 .md 구조

```markdown
# 2026년 2분기 솔루션 제안서

> 작성: 2026-05-11 | Butler AI  
> 원본: A사_제안서_2026Q2.pdf → 우리회사_제안서양식_2025.docx 기반  
> 변환 신뢰도: 88% | 매핑: 5/6

## 배경
...변환된 내용...

## 제안 내용
...변환된 내용...

## 기대 효과
...변환된 내용...

## 예산
...변환된 내용...

## 예산 세부
> ⚠️ 원본 문서에 해당 내용이 포함되지 않았습니다.

---
*Butler AI Document Transform — [원본 미포함 섹션: 예산 세부]*
```

### 7.3 사용자 인지 검증 매트릭스 (사전 명세)

| 검증 영역 | 기준 |
|---|---|
| **10초 이내 인지** | 결과 화면 진입 → 10초 안에 "우리 양식처럼 보이는지" 판단 가능 |
| **미매핑 섹션 즉시 인지** | ⚠️ 표시로 어느 부분이 비었는지 한눈에 파악 |
| **.docx 파일 열면 우리 양식처럼 보임** | 우리 양식 스타일(폰트, 여백, 헤더) 유지 |
| **원본 내용 누락 없음** | 외부 문서 핵심 내용이 결과에 모두 포함 |
| **인지 혼란 없음** | 변환된 내용과 미매핑 빈 섹션이 명확히 구분 |

---

## §8 D-2/D-3 학습 정착 영역 (NEW — 핵심 체크리스트)

> **이 섹션은 D-4 개발의 첫 커밋 전 필수 확인 사항입니다.**  
> D-2/D-3에서 반복된 결함이 재발하면 결함 추격 목표(30%) 초과가 확실합니다.

---

### §8.1 메인 화면 통합 의무 (카드 타일 + 활성화)

**현황**: `EmptyState.tsx` 카드 2번 `active: false` → 클릭 불가

**D-4 첫 커밋 필수 변경**:

```typescript
// butler-desktop/src/components/chat/EmptyState.tsx
{
  id: 2,
  Icon: ArrowRightLeft,
  title: '남의 문서 → 우리 양식',
  desc: '외부 문서 + 우리 과거 양식',
  mode: 'format_convert',
  active: true,  // ← false → true (첫 커밋 의무)
},
```

**체크리스트**:
- [ ] EmptyState.tsx `id: 2` `active: true`
- [ ] `data-testid="card-2"` 클릭 → 모달 오픈 확인
- [ ] App.tsx `CARD_MODE_MAP[2] = 'format_convert'` 유지 확인 (이미 있음)

---

### §8.2 모달 진입 라우팅 + 별도 오버레이 + 메인 화면 보존

**D-3 결함 패턴**: 모달이 메인 화면을 교체하거나 메인 화면 요소가 손상됨

**D-4 의무 패턴**:

```typescript
// App.tsx — format_convert 라우팅 추가
const [documentTransformModalOpen, setDocumentTransformModalOpen] = useState(false);

const handleCardSelect = (mode: string | null) => {
  const m = mode ?? 'free';
  setCardMode(m);
  if (m === 'accounting_classify') {
    setAccountingModalOpen(true);
  } else if (m === 'request_organize') {
    setRequestParsingModalOpen(true);
  } else if (m === 'format_convert') {
    setDocumentTransformModalOpen(true);  // ← 추가
  }
};

// JSX: 메인 화면 렌더링 유지 + 오버레이
{documentTransformModalOpen && (
  <DocumentTransformModal
    onClose={() => {
      setDocumentTransformModalOpen(false);
      setCardMode('free');
    }}
  />
)}
```

**오버레이 필수 사양** (WKWebView 인라인 스타일 의무):

```tsx
// DocumentTransformModal.tsx 최외곽 div
<div style={{
  position: 'fixed',      // ← Tailwind CSS 금지 (WKWebView 미적용)
  inset: 0,
  zIndex: 50,
  background: 'rgba(0,0,0,0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}}>
  <div style={{
    background: 'white',
    borderRadius: '12px',
    width: '90%',
    maxWidth: '680px',
    maxHeight: '90vh',
    overflowY: 'auto',
  }}>
    {/* 모달 내용 */}
  </div>
</div>
```

**체크리스트**:
- [ ] 모달 오픈 시 카드 그리드 (`data-testid="card-grid"`) 여전히 DOM에 존재
- [ ] `position: fixed` 반드시 인라인 스타일 (Tailwind className 금지)
- [ ] 모달 닫기 후 메인 화면 정상 복귀

---

### §8.3 UX 일관성 치수 사전 고정

**D-3 결함 패턴**: textarea 너무 작음, 버튼 비일관성, 분석 버튼 풀폭 아님

**D-4 의무 치수**:

| 요소 | 치수 |
|---|---|
| 파일 드롭존 (각) | 높이 100px 이상 |
| "변환하기" 버튼 | **풀폭 (width: 100%)**, primary 색상 (`#2563eb`) |
| "취소" 버튼 | `border: 1.5px solid #d1d5db`, background: white |
| 변환 옵션 체크박스 | 한 줄에 2개 |
| 결과 미리보기 영역 | 최대 높이 300px + overflow: auto |

**체크리스트**:
- [ ] "변환하기" 버튼 `width: '100%'` 확인
- [ ] "변환하기" 버튼 `background: '#2563eb'` (primary)
- [ ] 두 파일 미업로드 시 버튼 `disabled` + 연한 색상

---

### §8.4 아이콘 시스템 (Lucide — 이모지 완전 배제)

**D-3 결함 패턴**: 초기 구현에 이모지 사용 → 핫픽스 PR 발생

**D-4 의무 아이콘 매핑**:

| 위치 | 아이콘 | 금지 |
|---|---|---|
| 모달 헤더 | `<ArrowRightLeft size={20} style={{marginRight:'8px', verticalAlign:'middle', display:'inline'}} />` | 🔄 이모지 |
| 외부 문서 섹션 | `<FileText size={16} />` | 📄 이모지 |
| 우리 양식 섹션 | `<BookTemplate size={16} />` 또는 `<FileCheck size={16} />` | 📋 이모지 |
| 변환 성공 | `<CheckCircle size={16} color="#16a34a" />` | ✅ 이모지 |
| 미매핑 경고 | `<AlertTriangle size={16} color="#d97706" />` | ⚠️ 이모지 |
| .docx 다운로드 버튼 | `<Download size={16} />` | 📥 이모지 |

**체크리스트**:
- [ ] 모달 헤더 h2에 이모지 없음
- [ ] 모든 아이콘이 Lucide SVG (이모지 문자 없음)
- [ ] lucide-react import 사용 확인

---

### §8.5 진행 중 UI (Loader2 + 4단계 진행 바 + 중앙 정렬)

**D-3 결함 패턴**: CSS border spinner → Loader2 재작업 + 진행 바 추가 핫픽스

**D-4 의무 진행 중 UI** (인라인 스타일 의무):

```tsx
{phase.kind === 'processing' && (
  <div
    data-testid="loading-container"
    style={{
      padding: '48px 32px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '24px',
      minHeight: '300px',
    }}
  >
    <Loader2
      data-testid="loading-spinner"
      size={64}
      className="animate-spin"
      style={{ color: '#2563eb' }}
    />
    <div style={{ textAlign: 'center' }}>
      <p style={{ fontSize: '18px', fontWeight: 600, color: '#111827', margin: 0 }}>
        {phase.status}
      </p>
      <p style={{ fontSize: '13px', color: '#9ca3af', marginTop: '6px', marginBottom: 0 }}>
        단계 {phase.phaseNum} / 4
      </p>
    </div>
    {/* 4단계 진행 표시 */}
    <div data-testid="progress-steps" style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: '320px' }}>
      {[1, 2, 3, 4].map((n, idx) => (
        <React.Fragment key={n}>
          <div
            data-step={n}
            style={{
              width: '32px', height: '32px', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              backgroundColor: n <= phase.phaseNum ? '#2563eb' : '#e5e7eb',
              color: n <= phase.phaseNum ? 'white' : '#9ca3af',
              fontSize: '13px', fontWeight: 700, flexShrink: 0,
            }}
          >
            {n < phase.phaseNum ? '✓' : n}
          </div>
          {idx < 3 && (
            <div style={{ flex: 1, height: '3px', backgroundColor: n < phase.phaseNum ? '#2563eb' : '#e5e7eb' }} />
          )}
        </React.Fragment>
      ))}
    </div>
    {/* 선형 진행 바 */}
    <div style={{ width: '100%', maxWidth: '320px', height: '4px', backgroundColor: '#e5e7eb', borderRadius: '2px', overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${(phase.phaseNum / 4) * 100}%`, backgroundColor: '#2563eb', borderRadius: '2px', transition: 'width 0.3s ease' }} />
    </div>
    <button
      onClick={handleCancel}
      style={{
        padding: '10px 24px',
        border: '1.5px solid #d1d5db',
        borderRadius: '10px',
        background: 'white',
        color: '#374151',
        fontSize: '14px',
        fontWeight: 500,
        cursor: 'pointer',
      }}
    >
      취소
    </button>
  </div>
)}
```

**SSE phase 메시지**:

| phaseNum | status 텍스트 |
|---|---|
| 1 | "외부 문서 분석 중..." |
| 2 | "우리 양식 구조 분석 중..." |
| 3 | "내용 매핑 중..." |
| 4 | "문서 생성 중..." |

**체크리스트**:
- [ ] `data-testid="loading-spinner"` 에 `animate-spin` class
- [ ] `data-testid="progress-steps"` 에 `[data-step]` 4개
- [ ] `data-testid="loading-container"` `flexDirection: 'column'`, `alignItems: 'center'`
- [ ] 취소 버튼 border 1.5px solid

---

### §8.6 결과 영역 (섹션별 시각 구분 + 요약)

**D-3 결함 패턴**: 결과가 단일 텍스트 덩어리 → 섹션 분리 재작업

**D-4 의무 결과 구조**:

```
┌─ 요약 바 (상단 고정) ──────────────────────────────────┐
│  신뢰도: 88%   매핑: 5/6   미매핑: 1                  │
└──────────────────────────────────────────────────────┘
┌─ 섹션 카드 (매핑 완료) ─────────────────────────────┐
│  [섹션명]  ✅ 매핑 완료                              │
│  내용...                                            │
└──────────────────────────────────────────────────────┘
┌─ 섹션 카드 (미매핑) ────────────────────────────────┐
│  [섹션명]  ⚠️ 원본 미포함                          │
│  [내용 없음]                                        │
└──────────────────────────────────────────────────────┘
┌─ 다운로드 버튼 행 ──────────────────────────────────┐
│  [📥 .docx]  [📋 .md]  [👍 적합]  [👎 부적합]      │
└──────────────────────────────────────────────────────┘
```

**체크리스트**:
- [ ] 신뢰도 수치 상단에 즉시 표시
- [ ] 매핑 완료 / 미매핑 섹션이 시각적으로 구분 (색상 또는 아이콘)
- [ ] 다운로드 버튼 2개 모두 동작 (.docx / .md)
- [ ] 피드백 버튼 (👍/👎) 결과 하단에 표시

---

### §8.7 Sidecar Ready Check (wall-clock 60초)

**D-3 결함 패턴**: 첫 로딩 시 "TypeError: Load failed" 발생

**D-4 의무**: App.tsx의 현재 구현이 이미 wall-clock 60s 폴링을 포함하고 있습니다 (PR #698 codex P2 정정). 추가 작업 없음.

**확인만 필요**:
- [ ] `sidecarReady` 상태 기반 오버레이 동작 확인
- [ ] `DocumentTransformModal` 내부에서 fetch 실패 시 에러 핸들링 추가

```typescript
// DocumentTransformModal.tsx — fetch 에러 처리 (필수)
try {
  const res = await fetch(`${SIDECAR_BASE}/document_transform/transform_stream`, { ... });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  // ...
} catch (err) {
  setPhase({
    kind: 'error',
    message: err instanceof Error && err.name === 'AbortError'
      ? '취소되었습니다'
      : '변환 중 오류가 발생했습니다. 다시 시도해주세요.',
  });
}
```

---

### §8.8 의존성 파일 갱신 체크리스트 (PR #695 학습)

**D-3 결함 패턴**: python-docx / pdfminer.six 의존성 3개 파일에 누락 → 별도 핫픽스 PR

**D-4 의무 — 동일 의존성 4개 파일 모두 갱신**:

| 파일 | 추가 패키지 |
|---|---|
| `requirements.txt` | `python-docx>=0.8.11`, `pdfminer.six>=20221105` |
| `requirements-dev.txt` | (동일) |
| `requirements-serving.txt` | (동일) |
| `butler_pc_core/document_transform/` | 신규 모듈 `__init__.py` 포함 |

**체크리스트**:
- [ ] `requirements.txt` python-docx, pdfminer.six 추가
- [ ] `requirements-dev.txt` 동일 추가
- [ ] `requirements-serving.txt` 동일 추가
- [ ] `butler_pc_core/document_transform/__init__.py` 생성
- [ ] `butler_pc_core/document_transform/template_parser.py`
- [ ] `butler_pc_core/document_transform/content_extractor.py`
- [ ] `butler_pc_core/document_transform/output_renderer.py`

---

### §8.9 E2E 검증 의무 (자동 + GUI 동시)

**D-3 결함 패턴**: GUI 검증을 마지막에 몰아서 → 대규모 재작업

**D-4 의무**: **PR 단일 구성이므로 머지 전 E2E 검증 완료**

#### 자동 검증 (Claude Code 단계)

```bash
# 1. pytest 신규 테스트 포함 전체 통과
python -m pytest tests/accounting/ tests/request_parsing/ \
  tests/document_transform/ -v

# 2. Vitest 전체 통과
npx vitest run

# 3. TypeScript 오류 없음
cd butler-desktop && npx tsc --noEmit

# 4. Tauri 빌드 성공
npm run tauri build
```

#### sidecar 직접 검증 (Claude Code 단계)

```bash
# 백엔드 기동 후
curl -X POST http://127.0.0.1:5903/document_transform/transform_stream \
  -F "external_doc=@A사_제안서.pdf" \
  -F "template_doc=@우리회사_양식.docx" | head -50

# → SSE event: phase_start x4, event: complete 확인
```

#### GUI 시각 검증 (대표님 단계 — PR 머지 직후)

```
[T1] PDF 외부 문서 + .docx 양식
     예상: 섹션 구조 반영, 스타일 보존
     검증: "10초 이내 우리 양식처럼 보이는지" 판단

[T2] .docx 외부 문서 + .md 양식
     예상: 마크다운 섹션 구조 반영

[T3] 외부 문서 섹션이 양식보다 많을 때
     예상: 우리 양식에 없는 섹션은 무시 or 부록

[T4] 양식 섹션이 외부 문서보다 많을 때
     예상: 미매핑 섹션 ⚠️ 표시

[T5] 신뢰도 50% 미만 (내용 전혀 안 맞는 문서)
     예상: 경고 + "수동 보완 필요" 메시지
```

---

## §9 백엔드 API 사양

### 9.1 엔드포인트

```python
# butler_sidecar.py 추가

@app.post("/document_transform/transform_stream")
async def transform_stream(
    external_doc: UploadFile,
    template_doc: UploadFile,
    keep_header_footer: bool = Form(True),
    auto_fill_date: bool = Form(True),
):
    """
    SSE 스트리밍 변환
    
    Request: multipart/form-data
      - external_doc: 외부 문서 파일
      - template_doc: 우리 양식 파일
      - keep_header_footer: 우리 양식 헤더/푸터 유지 여부
      - auto_fill_date: 날짜/작성자 자동 채우기 여부
    
    SSE Events:
      event: phase_start
      data: {"phase": 0, "message": "외부 문서 분석 중..."}
      
      event: complete
      data: {"result_id": "dt_2026-05-11_xxxxx", "result": {...}}
      
      event: error
      data: {"message": "변환 중 오류가 발생했습니다"}
    """

@app.get("/document_transform/result/{result_id}/docx")
async def download_docx(result_id: str):
    """
    .docx 다운로드
    Content-Type: application/octet-stream
    Content-Disposition: inline; filename="변환결과.docx"
    """

@app.get("/document_transform/result/{result_id}/md")
async def download_md(result_id: str):
    """
    .md 다운로드
    Content-Type: text/plain; charset=utf-8
    """

@app.post("/document_transform/feedback")
async def feedback(result_id: str, payload: FeedbackPayload):
    """
    👍/👎 피드백 저장 (학습 데이터 수집)
    """
```

### 9.2 결과 TTL + 에러 처리

| 상황 | 처리 |
|---|---|
| 결과 캐시 TTL | 1800초 (30분) |
| 외부 문서 파싱 실패 | HTTP 400 + "파일을 읽을 수 없습니다" |
| 양식 파일 형식 오류 | HTTP 415 + ".docx 또는 .md 양식만 지원합니다" |
| LLM 추론 타임아웃 | 120초 후 HTTP 504 (문서 변환은 요청 파악보다 오래 걸림) |
| JSON Schema 검증 실패 | 자동 재시도 max 3회 → 실패 시 HTTP 502 |
| 결과 ID 미존재 | HTTP 404 |

### 9.3 응답 헤더 표준 (D-2/D-3 검증 패턴)

```python
{
    "Content-Type": "application/octet-stream",
    "Content-Disposition": "inline; filename=\"document_transform.docx\"",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}
```

---

## §10 Tauri 2.x 인프라

D-3에서 이미 완전 구축됨. 추가 변경 없이 동일 패턴 적용.

| 영역 | D-3 구축 상태 | D-4 작업 |
|---|---|---|
| `tauri-plugin-dialog` | ✅ 설치됨 | 추가 불필요 |
| `tauri-plugin-fs` | ✅ 설치됨 | 추가 불필요 |
| `capabilities/default.json` | ✅ fs:allow-write | 추가 불필요 |
| 다운로드 패턴 | ✅ D-3 검증됨 | 동일 복사 |

```typescript
// DocumentTransformModal.tsx — 다운로드 (D-3 검증 패턴 그대로)
import { save } from '@tauri-apps/plugin-dialog';
import { writeFile } from '@tauri-apps/plugin-fs';

async function downloadDocx(resultId: string) {
  const path = await save({
    defaultPath: `변환결과_${new Date().toISOString().slice(0, 10)}.docx`,
    filters: [{ name: 'Word Document', extensions: ['docx'] }],
  });
  if (!path) return;
  const res = await fetch(`${SIDECAR_BASE}/document_transform/result/${resultId}/docx`);
  const buffer = await res.arrayBuffer();
  await writeFile(path, new Uint8Array(buffer));
}
```

---

## §11 학습 루프

### 11.1 학습 데이터 저장 경로

```
learning_data/
└── document_transform/
    ├── positive/      ← 👍 피드백
    ├── negative/      ← 👎 피드백
    └── corrections/   ← 사용자 직접 수정
```

### 11.2 학습 데이터 형식

```json
{
  "id": "dt_2026-05-11_12345",
  "timestamp": "2026-05-11T14:30:00+09:00",
  "input": {
    "external_doc_type": "pdf",
    "template_doc_type": "docx",
    "external_section_count": 8,
    "template_section_count": 6
  },
  "output": {
    "sections": [...],
    "confidence": 0.88,
    "mapped_count": 5,
    "unmapped_count": 1
  },
  "user_feedback": {
    "rating": "positive",
    "problem_sections": null
  }
}
```

---

## §12 결함 추격 목표 + PR 계획

### 12.1 결함 추격 목표

| 사이클 | 목표 | 실적 |
|---|---|---|
| D-2 회계 분류 | — | 91.7% (12 PR 중 핫픽스 비율) |
| D-3 요청 파악 | 30% | **67%** (7 PR — 초과) |
| **D-4 문서 변환** | **30% 이하** | 목표 |
| D-5 이후 | 20% 이하 | 목표 |

D-3가 30% 목표에서 67%로 초과한 주요 원인:
1. active: false 시작 (핫픽스 1)
2. 이모지 헤더 (핫픽스 1)
3. CSS spinner (핫픽스 1)
4. 의존성 누락 (핫픽스 1)
5. WKWebView 스타일 (핫픽스 2)
6. GUI 검증 마지막 (핫픽스 1)

→ 위 6가지 모두 §8 체크리스트로 사전 차단.

### 12.2 D-4 PR 계획 (단일 PR)

| PR | 영역 | 추정 시간 |
|---|---|---|
| **#699** | D-4 본 기능 전체 (백엔드 + UI + 다운로드 통합) | 3~4일 |
| (#700 예비) | 핫픽스 (발생 시에만) | — |

### 12.3 [Claude Code 입력] — D-4 개발 시작

```
Butler AI D-4 카드 2 (ArrowRightLeft 남의 문서 → 우리 양식) 본 기능 개발을 시작합니다.

인계서: docs/handovers/D4_CARD2_DOCUMENT_TRANSFORM_v1.md

[브랜치] feat/d4-card2-document-transform
[베이스] main (현재 HEAD: PR #698 codex P2 머지 후)

[§8 체크리스트 — 첫 커밋 전 반드시 완료]
□ §8.1 EmptyState.tsx card 2 active: true
□ §8.4 아이콘 Lucide (이모지 X)
□ §8.7 sidecar fetch 에러 핸들링
□ §8.8 requirements 3파일 의존성 추가

[본 기능 구현]
1. butler_pc_core/document_transform/ 모듈 신규
   - content_extractor.py (외부 문서 → 텍스트)
   - template_parser.py (양식 → 섹션 목록)
   - output_renderer.py (섹션 + 스타일 → .docx / .md)

2. butler_sidecar.py 엔드포인트 추가
   - POST /document_transform/transform_stream (SSE)
   - GET /document_transform/result/{id}/docx
   - GET /document_transform/result/{id}/md
   - POST /document_transform/feedback

3. butler-desktop/src/components/chat/DocumentTransformModal.tsx 신규
   - §8.2 오버레이 패턴 (position: fixed 인라인)
   - §8.3 파일 드롭존 2개 (외부 문서 + 우리 양식)
   - §8.5 Loader2 + 4단계 진행 바 (D-3 코드 그대로)
   - §8.6 결과 화면 (섹션별 시각 구분)
   - 다운로드: .docx + .md (D-3 패턴 그대로)

4. App.tsx format_convert 라우팅 추가

[자동 검증]
- pytest: 기존 통과 + 신규 +8 → 전체 통과
- Vitest: 기존 168 + 신규 +5 → 전체 통과
- TypeScript: 오류 없음
- npm run tauri build: EXIT:0

[GUI 시각 검증 (대표님 단계)]
- T1~T5 시나리오 (§8.9)
- 10초 이내 "우리 양식처럼 보임" 판단

[보고 형식]
- 새 SHA
- §8 체크리스트 완료 항목
- pytest / Vitest 결과
- 빌드 결과 (.app 경로 + 마지막 5줄)
```

---

## 부록 A. 파일 구조 (D-4 신규)

```
butler_pc_core/
└── document_transform/
    ├── __init__.py
    ├── content_extractor.py     ← 외부 문서 텍스트 추출
    ├── template_parser.py       ← 양식 섹션 구조 분석
    ├── output_renderer.py       ← 변환 결과 .docx/.md 생성
    └── transform_pipeline.py   ← 전체 파이프라인 오케스트레이션

butler-desktop/src/
└── components/chat/
    └── DocumentTransformModal.tsx  ← 신규

tests/
└── document_transform/
    ├── __init__.py
    ├── conftest.py
    ├── test_content_extractor.py
    ├── test_template_parser.py
    ├── test_output_renderer.py
    └── test_transform_stream.py

butler-desktop/src/__tests__/
└── D4Card2Transform.test.tsx   ← 신규
```

## 부록 B. 관련 문서

| 문서 | 역할 |
|---|---|
| `D3_CARD1_REQUEST_PARSING_v1.md` | D-3 인계서 (D-4 구조의 원형) |
| `ACCOUNTING_LEARNING_CYCLE_v1.md` | D-2 학습 사이클 참조 |
| `PLATFORM_DEV_GUIDE_v1.md` | 개발지시서 v1 |
| `BUTLER_ARCHITECTURE_FINAL_v4.md` | 시스템 아키텍처 |

---

**작성**: 주식회사 에이티링크 / Butler AI  
**문서 버전**: v1.0 (2026-05-11)  
**다음 인계**: D-5 카드 3 (기존 문서 기반 새 초안)
