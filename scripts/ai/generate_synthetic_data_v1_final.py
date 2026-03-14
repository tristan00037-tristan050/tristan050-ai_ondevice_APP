"""
generate_synthetic_data_v1_final.py
AI-11 합성 데이터 파이프라인 — 최종 확정판

병합 전략:
  베이스  : generate_synthetic_data_v1 (v4) — 조합 템플릿 풀 (최대 225,000건+ 풀)
  수정    : _make_tool_call_pool 전면 교체
            → schema_v3.json 등록 9종만 사용
            → arguments 키/타입 schema 완전 일치 (additionalProperties=False 통과)
            → ko/en/mixed 각 135배·90배 풀 (count=500 기준)
  검증 체계: eval_butler_v3_5 (v39) 완전 호환

수정 이력:
  B1  "language" → "lang" 필드명 변경
  B2  completion raw dict → json.dumps() 직렬화
  B3  tool_call: action/params → tool_name/arguments
  B4  validate_record 조건식 단순화
  B5  load_tool_schema v3/v2 구조 모두 대응
  B6  SYNTHETIC_DATA_OK 판정: count × len(langs) 기준
  B10 completion_digest_sha256 → output_digest_sha256 통일
  B11 출력 파일명 v37 기준 통일
  B12 기능명 v37 기준 통일
       conversation→dialogue / summarization→summarize
       rewriting→rewrite / extraction→retrieval_transform
  D1  dialogue mixed 풀 6→12 템플릿 확장 (4,800건+)
  D2  tool_call ko/en/mixed 전체 tool_name+arguments 구조 일원화
  D3  validate_record에 split, format 검증 추가
  D4  extraction 내부 random도 seed 영향권 유지
  FINAL  _make_tool_call_pool 전면 재설계
         schema_v3 미등록 5종(get_schedule/send_message/search_file/set_alarm/create_report)
         → schema_v3 등록 9종으로 교체

실행:
  python3 scripts/ai/generate_synthetic_data_v1_final.py \\
      --functions all --lang ko en mixed --count 500 \\
      --out data/synthetic/ --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path
from typing import Any

# ── 스키마 경로 ────────────────────────────────────────────────────────────
SCHEMA_PATH_V3 = Path("schemas/tool_call_schema_v3.json")
SCHEMA_PATH_V2 = Path("schemas/tool_call_schema_v2.json")

UNIQUE_RATIO_MIN = 0.85

# ── 기능명 (v37 기준) ──────────────────────────────────────────────────────
FUNCTIONS = [
    "dialogue",
    "summarize",
    "rewrite",
    "tool_call",
    "policy_sensitive",
    "retrieval_transform",
]


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


# ── load_tool_schema — v3/v2 모두 대응 ────────────────────────────────────
def load_tool_schema() -> dict:
    """
    v3: {"tools": [{"name": "add_schedule", "arguments": {...}, "required": [...]}, ...]}
    v2: {"registered_actions": [...], "tools": [{"tools": [...]}]}
    반환 schema에 반드시 "registered_actions": [str, ...] 키 존재.
    """
    path = SCHEMA_PATH_V3 if SCHEMA_PATH_V3.exists() else SCHEMA_PATH_V2
    if not path.exists():
        raise RuntimeError(
            f"SCHEMA_MISSING: v3={SCHEMA_PATH_V3}, v2={SCHEMA_PATH_V2}"
        )
    schema = json.loads(path.read_text(encoding="utf-8"))

    if "tools" in schema and isinstance(schema["tools"], list):
        first = schema["tools"][0] if schema["tools"] else {}
        # v2 nested 구조 평탄화
        if "tools" in first:
            flat = []
            for cat in schema["tools"]:
                for t in cat.get("tools", []):
                    flat.append(t)
            schema["tools"] = flat

    # registered_actions 키 보장 (v2 호환 + 이름 기반)
    if "registered_actions" not in schema:
        schema["registered_actions"] = [
            t["name"]
            for t in schema.get("tools", [])
            if "name" in t
        ]
    return schema


# ═══════════════════════════════════════════════════════════════
# 공통 변수 풀
# ═══════════════════════════════════════════════════════════════

KO_NAMES = [
    "김철수", "이영희", "박민준", "최수진", "정우진",
    "한지수", "윤서연", "임현우", "송미래", "강도현",
    "오지훈", "백서현", "류성민", "신예진", "황준혁",
    "조아름", "전민서", "문성준", "노지현", "심재원",
]
EN_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Edward",
    "Fiona", "George", "Hannah", "Ivan", "Julia",
    "Kevin", "Laura", "Michael", "Nancy", "Oscar",
    "Patricia", "Quinn", "Rachel", "Steven", "Tina",
]
KO_DEPTS = [
    "개발팀", "마케팅팀", "영업팀", "기획팀", "인사팀",
    "재무팀", "법무팀", "운영팀", "디자인팀", "데이터팀",
    "고객지원팀", "전략팀", "구매팀", "R&D팀", "품질팀",
]
EN_DEPTS = [
    "Engineering", "Marketing", "Sales", "Planning", "HR",
    "Finance", "Legal", "Operations", "Design", "Data",
    "Support", "Strategy", "Procurement", "R&D", "QA",
]
KO_TOPICS = [
    "보고서 작성", "회의 일정", "프로젝트 현황", "예산 검토",
    "인사 평가", "업무 인수인계", "고객 대응", "시스템 장애",
    "제품 출시", "계약 검토", "출장 신청", "교육 이수",
    "성과 목표", "팀 워크숍", "분기 마감", "채용 공고",
    "업무 자동화", "보안 점검", "데이터 분석", "서비스 개선",
    "비용 절감", "파트너십", "규정 준수", "문서 관리", "품질 개선",
]
EN_TOPICS = [
    "report writing", "meeting schedule", "project status", "budget review",
    "performance evaluation", "handover", "client response", "system outage",
    "product launch", "contract review", "travel request", "training completion",
    "KPI setting", "team workshop", "quarter close", "job posting",
    "process automation", "security audit", "data analysis", "service improvement",
    "cost reduction", "partnership", "compliance", "document management",
    "quality improvement",
]
DATES = [
    "2026-03-15", "2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19",
    "2026-03-22", "2026-03-23", "2026-03-24", "2026-03-25", "2026-03-26",
    "2026-04-01", "2026-04-07", "2026-04-14", "2026-04-21", "2026-04-28",
]
TIMES = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00", "17:00"]
KO_LOCS = [
    "서울 강남구", "서울 여의도", "서울 마포구", "부산 해운대", "인천 송도",
    "성남 판교", "수원 광교", "대전 유성", "대구 수성구", "광주 상무지구",
]


# ═══════════════════════════════════════════════════════════════
# 기능별 풀 생성
# ═══════════════════════════════════════════════════════════════

# ── dialogue ─────────────────────────────────────────────────────────────
def _make_dialogue_pool(lang: str) -> list[tuple[str, str]]:
    pairs = []

    if lang == "ko":
        prompt_templates = [
            "{name}에게 {topic}에 대해 어떻게 시작하면 좋을지 알려줘.",
            "{dept}의 {topic} 진행 상황을 정리해줘.",
            "{topic} 관련해서 {name}이(가) 물어봤는데 뭐라고 답하면 돼?",
            "{name}과 {topic} 협의할 때 주요 포인트가 뭐야?",
            "{dept}에서 {topic}을 담당하는 방법 설명해줘.",
            "{topic} 관련 {dept} 회의 진행 순서를 알려줘.",
            "{name}한테 {topic} 업무를 배분하려면 어떻게 해야 해?",
            "다음 주 {topic} 준비를 위해 {dept}와 협력할 방법은?",
            "{topic} 완료 보고를 {name}에게 어떻게 전달하면 좋을까?",
            "{dept}가 {topic} 이슈를 발견했을 때 대응 절차를 알려줘.",
            "{name}이(가) {topic}에 대해 모르는 경우 어떻게 안내해?",
            "{topic}으로 인한 {dept} 업무 지연 시 처리 방법은?",
        ]
        completion_templates = [
            "{name}님께 {topic}을(를) 시작하기 전에 목표와 범위를 명확히 하고, 관련 부서와 사전 조율하도록 안내하세요.",
            "{dept}의 {topic} 현황은 현재 일정대로 진행 중이며, 주요 마일스톤을 점검 후 보고하는 것이 좋습니다.",
            "{topic}에 대한 {name}님 질문은 관련 정책과 절차를 기반으로 단계별로 설명해 드리면 됩니다.",
            "{name}님과 {topic} 협의 시 우선순위, 일정, 예산, 담당자 4가지를 핵심으로 논의하세요.",
            "{dept}에서 {topic}을(를) 담당하려면 관련 교육을 이수하고, 담당자와 업무 범위를 조율하세요.",
            "{dept}의 {topic} 회의는 현황 보고, 이슈 논의, 다음 액션 확인 순서로 진행합니다.",
            "{name}님께 {topic} 업무를 배분할 때는 역량과 업무 부하를 고려하여 명확한 기한을 설정하세요.",
            "다음 주 {topic} 준비를 위해 {dept}와 주간 싱크 미팅을 잡고 역할을 분담하세요.",
            "{name}님께 {topic} 완료 보고는 결과 요약, 잔여 과제, 후속 조치 순으로 전달하면 됩니다.",
            "{dept}에서 {topic} 이슈 발견 시 즉시 팀장에게 보고하고, 영향 범위를 파악한 후 대응 방안을 수립하세요.",
        ]
        for pt in prompt_templates:
            for ct in completion_templates:
                for name in KO_NAMES[:10]:
                    for dept in KO_DEPTS[:5]:
                        for topic in KO_TOPICS[:5]:
                            pairs.append((
                                pt.format(name=name, dept=dept, topic=topic),
                                ct.format(name=name, dept=dept, topic=topic),
                            ))

    elif lang == "en":
        prompt_templates = [
            "How should I start talking to {name} about {topic}?",
            "Summarize the status of {topic} in the {dept} team.",
            "{name} asked me about {topic}. What should I say?",
            "What are the key points when discussing {topic} with {name}?",
            "Explain how {dept} handles {topic} responsibilities.",
            "What is the meeting agenda for {topic} in {dept}?",
            "How do I assign {topic} tasks to {name}?",
            "How should {dept} collaborate to prepare for {topic} next week?",
            "How should I deliver the {topic} completion report to {name}?",
            "What's the response procedure when {dept} finds a {topic} issue?",
            "How do I guide {name} who doesn't know about {topic}?",
            "How to handle a {dept} work delay caused by {topic}?",
        ]
        completion_templates = [
            "When starting a conversation with {name} about {topic}, clarify the objectives and scope first, then coordinate with relevant teams.",
            "The {dept} {topic} status is on track. Review key milestones and prepare a brief update.",
            "For {name}'s question about {topic}, explain it step-by-step based on company policy and procedures.",
            "When discussing {topic} with {name}, focus on priority, timeline, budget, and owner as the four key points.",
            "To handle {topic} in {dept}, complete relevant training and clarify the scope with your manager.",
            "The {dept} {topic} meeting follows: status update, issue discussion, and action items confirmation.",
            "When assigning {topic} to {name}, consider their workload and set a clear deadline.",
            "To prepare {dept} for {topic} next week, schedule a sync meeting and divide responsibilities clearly.",
            "Deliver the {topic} completion report to {name} with a results summary, remaining tasks, and follow-up actions.",
            "When {dept} finds a {topic} issue, report to the manager immediately, assess impact, and create a response plan.",
        ]
        for pt in prompt_templates:
            for ct in completion_templates:
                for name in EN_NAMES[:10]:
                    for dept in EN_DEPTS[:5]:
                        for topic in EN_TOPICS[:5]:
                            pairs.append((
                                pt.format(name=name, dept=dept, topic=topic),
                                ct.format(name=name, dept=dept, topic=topic),
                            ))

    else:  # mixed — D1: 12개 템플릿으로 확장
        templates = [
            ("Please help {name} with {topic} in {dept}.", "{name}님의 {dept} {topic} 업무를 도와드리겠습니다. 먼저 목표를 확인해보겠습니다."),
            ("{dept}의 {topic} status를 알려줘.", "The {dept} team's {topic} status is currently on schedule. 세부 내용을 확인하겠습니다."),
            ("{name}에게 {topic} meeting을 설정해줘.", "I'll help set up a {topic} meeting with {name}. 일정을 확인하겠습니다."),
            ("Can you explain {topic} to {name} in {dept}?", "{dept}의 {name}님께 {topic}을(를) 단계별로 설명해 드리겠습니다."),
            ("{name}이(가) {topic}을 완료했는지 check해줘.", "I'll check if {name} has completed {topic}. 확인 후 알려드리겠습니다."),
            ("Help me draft {topic} 보고서 for {dept}.", "{dept}를 위한 {topic} 보고서 초안을 작성해드리겠습니다."),
            ("{dept} {topic} progress를 {name}에게 공유해줘.", "{name}님께 {dept}의 {topic} 진행 상황을 공유하겠습니다."),
            ("{name}에게 {topic} 관련 follow-up을 요청해줘.", "I'll send a {topic} follow-up request to {name}. 내용을 정리하겠습니다."),
            ("{dept}의 {topic} issue를 어떻게 resolve할까?", "{dept}의 {topic} 이슈를 해결하려면 먼저 원인을 파악해야 합니다. Let me outline the steps."),
            ("What's the best way to brief {name} on {topic}?", "{name}님께 {topic}을(를) 간결하게 브리핑하려면 핵심 포인트 3가지를 중심으로 전달하세요."),
            ("{name}과 {dept}의 {topic} 협업 방안을 알려줘.", "Here's a collaboration plan for {name} and {dept} on {topic}: 먼저 공동 목표를 설정하세요."),
            ("How do I escalate {topic} to {name} in {dept}?", "{dept}의 {name}님께 {topic}을(를) 에스컬레이션할 때는 현황·영향·요청사항 순으로 전달하세요."),
        ]
        for pt, ct in templates:
            for name in KO_NAMES[:8]:
                for dept in KO_DEPTS[:5]:
                    for topic in KO_TOPICS[:8]:
                        pairs.append((
                            pt.format(name=name, dept=dept, topic=topic),
                            ct.format(name=name, dept=dept, topic=topic),
                        ))

    return pairs


# ── summarize ─────────────────────────────────────────────────────────────
def _make_summarize_pool(lang: str) -> list[tuple[str, str]]:
    pairs = []

    if lang == "ko":
        doc_templates = [
            "{topic}는 {dept}에서 핵심 업무로, 매 분기마다 성과를 측정하고 개선 방안을 도출합니다. 주요 담당자는 {name}이며, 관련 팀과 협업하여 진행합니다.",
            "{dept}의 {topic} 프로젝트는 {date}까지 완료 예정이며, 현재 진행률은 70%입니다. {name}이(가) 주도하고 있으며 예산 범위 내에서 진행 중입니다.",
            "이번 분기 {topic} 성과 보고: {dept}는 목표 대비 115% 달성하였으며, 주요 성공 요인은 {name}의 리더십과 팀 협업입니다.",
            "{name}은(는) {dept}에서 {topic} 담당자로서 일일 업무 현황을 보고하고, 주간 단위로 진행 상황을 공유합니다.",
            "{topic} 정책 업데이트: {dept}는 {date}부터 새로운 절차를 시행합니다. 변경 사항은 {name}을(를) 통해 전달됩니다.",
        ]
        summary_templates = [
            "{dept}의 {topic}: {name} 담당, 정기 성과 측정 및 개선 진행.",
            "{dept} {topic} 프로젝트 70% 진행 중, {date} 완료 목표, {name} 주도.",
            "{dept} {topic}: 목표 115% 달성, {name} 리더십이 핵심.",
            "{name}/{dept}: {topic} 일일 보고, 주간 공유.",
            "{dept} {topic} 정책: {date}부터 새 절차 시행, {name} 담당.",
            "{topic} 핵심: {name}({dept}) 주도, {date} 기준 운영.",
            "{dept} {topic} 현황: {name} 책임, 일정/예산 준수.",
            "{name}이(가) {dept}에서 {topic}을(를) {date}까지 완료 목표로 추진.",
            "{dept}의 {topic} 업무는 {name}이(가) 담당하며 정상 진행 중.",
            "{topic}({dept}): {name} 주도, 주요 일정 {date}.",
        ]
        for dt in doc_templates:
            for st in summary_templates:
                for name in KO_NAMES[:8]:
                    for dept in KO_DEPTS[:5]:
                        for topic in KO_TOPICS[:5]:
                            for date in DATES[:3]:
                                pairs.append((
                                    "다음을 1~2문장으로 요약하세요: " + dt.format(name=name, dept=dept, topic=topic, date=date),
                                    st.format(name=name, dept=dept, topic=topic, date=date),
                                ))

    elif lang == "en":
        doc_templates = [
            "The {topic} project in {dept} is led by {name} and is scheduled for completion by {date}. Current progress is at 70% with budget on track.",
            "{dept}'s {topic} initiative this quarter achieved 115% of target. Key success factors include {name}'s leadership and cross-team collaboration.",
            "{name} from {dept} handles {topic} responsibilities, submitting daily status reports and weekly progress updates.",
            "Policy update for {topic} in {dept}: New procedures take effect on {date}. All changes will be communicated through {name}.",
            "The {topic} review in {dept} showed that {name}'s team exceeded expectations, delivering results ahead of the {date} deadline.",
        ]
        summary_templates = [
            "{dept} {topic}: Led by {name}, on track for {date} completion.",
            "{dept} {topic}: 115% of target achieved, {name}'s leadership cited.",
            "{name}/{dept}: Daily {topic} reporting, weekly updates.",
            "{dept} {topic} policy: New procedures from {date}, via {name}.",
            "{name}'s {dept} team exceeded {topic} targets before {date}.",
            "{topic} ({dept}): {name} responsible, {date} milestone.",
            "{dept} {topic} 70% complete, {name} leading, {date} target.",
            "{name} manages {dept} {topic}: daily reports, policy compliant.",
            "{topic} update: {dept} team under {name} ahead of schedule.",
            "{dept}/{name}: {topic} complete by {date}, within budget.",
        ]
        for dt in doc_templates:
            for st in summary_templates:
                for name in EN_NAMES[:8]:
                    for dept in EN_DEPTS[:5]:
                        for topic in EN_TOPICS[:5]:
                            for date in DATES[:3]:
                                pairs.append((
                                    "Summarize in 1-2 sentences: " + dt.format(name=name, dept=dept, topic=topic, date=date),
                                    st.format(name=name, dept=dept, topic=topic, date=date),
                                ))

    else:  # mixed
        templates = [
            ("다음을 요약해줘: {name} is leading {topic} in {dept} with {date} deadline.", "{name}({dept}) {topic} 프로젝트: {date} 완료 목표."),
            ("Summarize: {dept}의 {topic}은 {name}이(가) 담당, {date}까지 진행.", "{dept} {topic}: {name} responsible, target {date}."),
            ("요약: {name}'s {dept} team completed {topic} ahead of schedule.", "{name}({dept}) {topic}: 일정 내 완료."),
        ]
        for pt, ct in templates:
            for name in KO_NAMES[:8]:
                for dept in KO_DEPTS[:5]:
                    for topic in KO_TOPICS[:8]:
                        for date in DATES[:5]:
                            pairs.append((
                                pt.format(name=name, dept=dept, topic=topic, date=date),
                                ct.format(name=name, dept=dept, topic=topic, date=date),
                            ))

    return pairs


# ── rewrite ───────────────────────────────────────────────────────────────
def _make_rewrite_pool(lang: str) -> list[tuple[str, str]]:
    if lang == "ko":
        raw_pol_templates = [
            ("{name}한테 빨리 해달라고 해줘.",         "{name}님께 빠른 처리를 부탁드리겠습니다."),
            ("{name} 보고서가 형편없어.",              "{name}님 보고서 품질 개선이 필요해 보입니다."),
            ("{dept} 이거 왜 이렇게 늦어?",            "{dept} 진행 상황을 공유해 주실 수 있을까요?"),
            ("{name}한테 지금 당장 오라고 해.",         "{name}님께 가능하시면 잠시 자리 부탁드린다고 전해주세요."),
            ("{dept} 이게 말이 돼?",                   "{dept} 이 부분에 대해 좀 더 검토가 필요할 것 같습니다."),
            ("{name} 대충 하지 마.",                    "{name}님께 정확한 처리를 부탁드립니다."),
            ("{name}은(는) 왜 이렇게 모르냐?",          "{name}님께 이 부분을 좀 더 명확히 안내해 드리겠습니다."),
            ("{dept}는 그냥 시키는 대로 해.",            "{dept}는 지시 사항을 정확히 따라주시면 감사하겠습니다."),
            ("{name} 언제 끝나?",                      "{name}님의 완료 예정 시간을 알려주시면 감사하겠습니다."),
            ("{name} 이거 다시 해.",                    "{name}님께 다시 한번 검토해 주시면 감사하겠습니다."),
            ("{dept} 제대로 해.",                       "{dept}에서 정확하게 처리해 주시면 감사하겠습니다."),
            ("{name} 왜 보고 안 해?",                   "{name}님의 보고 일정을 공유해 주시면 좋을 것 같습니다."),
            ("{dept} 그게 뭐야?",                       "{dept} 이 부분을 좀 더 설명해 주시겠어요?"),
            ("{name} 이건 아니잖아.",                    "{name}님, 이 방향은 재검토가 필요해 보입니다."),
            ("{dept} 왜 못 해?",                        "{dept}에서 어떤 어려운 점이 있는지 공유해 주시겠어요?"),
            ("{name} 빨리빨리.",                         "{name}님께 신속한 처리를 부탁드립니다."),
            ("{dept} 틀렸잖아.",                         "{dept} 이 부분에 수정이 필요해 보입니다."),
            ("{name} 할 수 있어?",                      "{name}님의 가능 여부를 확인해 주시겠어요?"),
            ("{dept} 좀 잘 해봐.",                      "{dept} 더 좋은 결과를 위해 노력해 주시면 감사하겠습니다."),
            ("{name} 이걸 왜 모르냐.",                   "{name}님, 이 부분을 좀 더 명확히 이해하고 싶습니다."),
            ("{dept} 다시 확인해봐.",                    "{dept} 한 번 더 확인해 주시면 감사하겠습니다."),
            ("{name} 신경 꺼.",                          "해당 사항은 {name}님의 업무 범위가 아닌 것 같습니다."),
            ("{dept} 맞게 해.",                          "{dept}에서 정확하게 수행해 주시면 감사하겠습니다."),
            ("{name} 왜 이래?",                          "{name}님, 어떤 점이 문제인지 공유해 주시겠어요?"),
            ("{dept} 해줄 수 있어?",                     "{dept}에서 가능하다면 처리해 주시겠어요?"),
            ("{name} 이 보고서 좀 고쳐.",                 "{name}님의 보고서를 함께 개선하면 좋을 것 같습니다."),
        ]
        prompt_t = [
            "{name}/{dept}에게 전달할 때 공손하게: {raw}",
            "업무 상황에 맞게 정제해주세요: {raw}",
            "다음을 전문적이고 공손한 표현으로: {raw}",
            "아래 문장을 정중한 표현으로 바꿔주세요: {raw}",
        ]
        pairs = []
        for pt in prompt_t:
            for raw_t, pol in raw_pol_templates:
                for name in KO_NAMES[:10]:
                    for dept in KO_DEPTS[:5]:
                        raw = raw_t.format(name=name, dept=dept)
                        pol_f = pol.format(name=name, dept=dept)
                        pairs.append((pt.format(raw=raw, name=name, dept=dept), pol_f))
        return pairs

    elif lang == "en":
        raw_pol_templates = [
            ("Tell {name} to do it now.",                  "Please ask {name} to prioritize this at their earliest convenience."),
            ("{name}'s report from {dept} is terrible.",   "{name}'s report from {dept} could benefit from significant improvements."),
            ("Why is {dept} taking so long?",              "Could {dept} provide an update on the current progress?"),
            ("Tell {name} to come here immediately.",       "Could you ask {name} to come over when they have a moment?"),
            ("This doesn't make sense, {dept}.",           "{dept}, I'd like to better understand the reasoning behind this approach."),
            ("{name}, stop being sloppy.",                 "{name}, please handle this with greater accuracy and care."),
            ("Why doesn't {name} know this?",              "Allow me to provide {name} with some clarification on this matter."),
            ("{dept}, just follow orders.",                "{dept}, please follow the instructions as provided."),
            ("When will {name} be done?",                  "Could {name} share the expected completion time?"),
            ("{name}, redo this.",                         "{name}, please review and revise this at your convenience."),
            ("{dept}, do it properly.",                    "{dept}, could you ensure this is completed accurately?"),
            ("Why didn't {name} report?",                  "Could {name} share the reporting timeline?"),
            ("{dept}, what is this?",                      "{dept}, could you elaborate on what this means?"),
            ("{name}, this is not acceptable.",            "{name}, this approach may need to be reconsidered."),
            ("Why can't {dept} do it?",                    "Could {dept} share what challenges they're facing?"),
            ("{name}, hurry up.",                          "{name}, please expedite this when possible."),
            ("{dept}, you're wrong.",                      "{dept}, it seems this part may need revision."),
            ("Can {name} even do this?",                   "Could {name} confirm if this is feasible?"),
            ("{dept}, try to do better.",                  "{dept}, please do your best to improve the outcome."),
            ("{name}, double-check this.",                 "{name}, please verify this one more time."),
            ("{dept}, stay out of it.",                    "{dept}, this may be outside the current scope of responsibility."),
            ("{name}, do it right.",                       "{name}, please complete this as accurately as possible."),
            ("What's wrong with {dept}?",                  "Could {dept} share what the issue is?"),
            ("{name}, can you help me?",                   "{name}, could you assist with this when possible?"),
            ("{dept}, don't be vague.",                    "{dept}, could you provide more specific details?"),
            ("{name}, fix this now.",                      "{name}, please address this correction at your earliest convenience."),
        ]
        prompt_t = [
            "Rewrite more politely for {name} in {dept}: {raw}",
            "Make this more professional: {raw}",
            "Rephrase for a business context with {name}: {raw}",
            "Make this more respectful: {raw}",
        ]
        pairs = []
        for pt in prompt_t:
            for raw_t, pol in raw_pol_templates:
                for name in EN_NAMES[:10]:
                    for dept in EN_DEPTS[:5]:
                        raw = raw_t.format(name=name, dept=dept)
                        pol_f = pol.format(name=name, dept=dept)
                        pairs.append((pt.format(raw=raw, name=name, dept=dept), pol_f))
        return pairs

    else:  # mixed
        raw_pol_templates = [
            ("{name}한테 이거 ASAP으로 fix해줘.",         "{name}님께 이 사항을 최대한 신속히 수정해 주시길 부탁드립니다."),
            ("{dept} report 형편없어.",                   "{dept} report could benefit from significant improvements."),
            ("Hurry up, {name} 빨리 해.",                 "{name}님께 빠른 처리를 부탁드립니다. Please expedite when possible."),
            ("{dept} 그거 wrong이야.",                    "{dept}에서 해당 부분 수정이 필요합니다. There may be an error to address."),
            ("Why {name} 이렇게 늦어?",                   "Could {name} share the status? 진행 상황을 알려주시겠어요?"),
            ("{name} 이거 redo해줘.",                     "Please ask {name} to review and revise this. 다시 검토 부탁드립니다."),
            ("{dept}에 바로 come here 해달라고 해.",       "Would {dept} be available to come over? 잠시 시간 내주시겠어요?"),
            ("{name}한테 Can you make this more 공손하게?", "{name}님께 해당 내용을 정중한 표현으로 다듬어 주시도록 안내하겠습니다."),
        ]
        prompt_t = [
            "{name}/{dept}: 다음을 더 공손하게 바꿔줘: {raw}",
            "Rephrase more politely for {name}: {raw}",
            "정중하게 표현해줘 ({dept} 맥락): {raw}",
            "Make this professional ({name}): {raw}",
        ]
        pairs = []
        for pt in prompt_t:
            for raw_t, pol in raw_pol_templates:
                for name in KO_NAMES[:10]:
                    for dept in KO_DEPTS[:5]:
                        raw = raw_t.format(name=name, dept=dept)
                        pol_f = pol.format(name=name, dept=dept)
                        pairs.append((pt.format(raw=raw, name=name, dept=dept), pol_f))
        return pairs


# ── tool_call — FINAL: schema_v3 9종 완전 호환 ───────────────────────────
# schema_v3 등록 tools (arguments 키 정확히 일치):
#   get_weather   : location(req), date
#   add_schedule  : title(req), date(req), time, location
#   send_email    : to(req), subject(req), body(req)
#   search_contact: name(req)
#   summarize_doc : document_text(req), target_length
#   set_volume    : level(req)
#   toggle_wifi   : enabled(req)
#   open_file     : path(req)
#   save_memo     : title(req), content(req)

def _make_tool_call_pool(lang: str, schema: dict) -> list[tuple[str, str]]:
    pairs = []

    if lang == "ko":
        templates = [
            # get_weather — 3종
            ("오늘 {loc}의 날씨를 조회하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": "today"}}),
            ("내일 {loc} 날씨 예보를 조회하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": "tomorrow"}}),
            ("{date} {loc} 날씨 정보를 요청하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": d}}),
            # add_schedule — 3종
            ("{date} {time}에 {name}과 {topic} 회의를 추가하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": f"{n}과 {t} 회의", "date": d, "time": ti}}),
            ("{date} {time}에 {topic} 일정을 {loc}에서 추가하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": t, "date": d, "time": ti, "location": loc}}),
            ("{topic} 팀 미팅을 {date}에 추가하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": f"{t} 팀 미팅", "date": d}}),
            # send_email — 2종
            ("{name}에게 {topic} 관련 이메일을 보내는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.replace(' ','')}@company.com", "subject": f"{t} 관련", "body": f"안녕하세요, {t} 관련하여 연락드립니다."}}),
            ("{topic} 주간 업데이트를 {name}에게 메일로 보내는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.replace(' ','')}@company.com", "subject": f"주간 업데이트: {t}", "body": f"{t} 진행 상황을 공유드립니다."}}),
            # search_contact — 2종
            ("{name}의 연락처를 조회하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "search_contact", "arguments": {"name": n}}),
            ("{topic} 담당자 {name}의 정보를 검색하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "search_contact", "arguments": {"name": n}}),
            # summarize_doc — 2종
            ("{topic} 문서를 짧게 요약하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "summarize_doc", "arguments": {"document_text": f"{t} 관련 보고 문서입니다.", "target_length": "short"}}),
            ("{topic} 보고서 요약을 요청하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "summarize_doc", "arguments": {"document_text": f"{t} 진행 보고서입니다."}}),
            # set_volume — 1종
            ("볼륨을 50으로 설정하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "set_volume", "arguments": {"level": 50}}),
            # toggle_wifi — 1종
            ("Wi-Fi를 끄는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "toggle_wifi", "arguments": {"enabled": False}}),
            # open_file — 2종
            ("{topic} 파일을 여는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "open_file", "arguments": {"path": f"/documents/{t.replace(' ','_')}.txt"}}),
            ("리포트 파일 /tmp/report.txt를 여는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "open_file", "arguments": {"path": "/tmp/report.txt"}}),
            # save_memo — 2종
            ("{topic} 관련 메모를 저장하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "save_memo", "arguments": {"title": f"{t} 메모", "content": f"{t} 관련 주요 내용을 기록합니다."}}),
            ("{name}과의 {topic} 논의 내용을 메모로 저장하는 tool_call JSON을 작성하세요. JSON만 출력하세요.",
             lambda n, d, t, ti, loc: {"tool_name": "save_memo", "arguments": {"title": f"{n} {t} 논의", "content": f"{n}님과 {t}에 대해 논의한 내용입니다."}}),
        ]
        for pt, out_fn in templates:
            for name in KO_NAMES[:10]:
                for dept in KO_DEPTS[:5]:
                    for topic in KO_TOPICS[:5]:
                        for date in DATES[:5]:
                            for time_ in TIMES[:3]:
                                for loc in KO_LOCS[:3]:
                                    args = out_fn(name, date, topic, time_, loc)
                                    pairs.append((
                                        pt.format(name=name, dept=dept, topic=topic, date=date, time=time_, loc=loc),
                                        args,
                                    ))

    elif lang == "en":
        templates = [
            # get_weather — 3종
            ("Write a tool_call JSON to get today's weather in {loc}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": "today"}}),
            ("Write a tool_call JSON to check tomorrow's weather in {loc}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": "tomorrow"}}),
            ("Write a tool_call JSON to get the weather for {date} in {loc}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": d}}),
            # add_schedule — 3종
            ("Write a tool_call JSON to schedule a {topic} meeting with {name} on {date} at {time}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": f"{t} meeting with {n}", "date": d, "time": ti}}),
            ("Write a tool_call JSON to add a {topic} event at {loc} on {date}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": t, "date": d, "location": loc}}),
            ("Write a tool_call JSON to book a {topic} team meeting on {date} at {time}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": f"{t} team meeting", "date": d, "time": ti}}),
            # send_email — 2종
            ("Write a tool_call JSON to send {name} an email about {topic}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.lower().replace(' ','.')}@company.com", "subject": f"Re: {t}", "body": f"Hi {n}, regarding {t}."}}),
            ("Write a tool_call JSON to send a weekly {topic} update email to {name}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.lower().replace(' ','.')}@company.com", "subject": f"Weekly Update: {t}", "body": f"Here is the latest update on {t}."}}),
            # search_contact — 2종
            ("Write a tool_call JSON to look up {name}'s contact. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "search_contact", "arguments": {"name": n}}),
            ("Write a tool_call JSON to find contact info for {name} in {dept}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "search_contact", "arguments": {"name": n}}),
            # summarize_doc — 2종
            ("Write a tool_call JSON to summarize the {topic} document in short form. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "summarize_doc", "arguments": {"document_text": f"This document covers {t}.", "target_length": "short"}}),
            ("Write a tool_call JSON to get a brief summary of the {topic} report. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "summarize_doc", "arguments": {"document_text": f"{t} progress report."}}),
            # set_volume — 1종
            ("Write a tool_call JSON to set the volume to 50. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "set_volume", "arguments": {"level": 50}}),
            # toggle_wifi — 1종
            ("Write a tool_call JSON to turn off Wi-Fi. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "toggle_wifi", "arguments": {"enabled": False}}),
            # open_file — 2종
            ("Write a tool_call JSON to open the {topic} file. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "open_file", "arguments": {"path": f"/documents/{t.replace(' ','_')}.txt"}}),
            ("Write a tool_call JSON to open /tmp/report.txt. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "open_file", "arguments": {"path": "/tmp/report.txt"}}),
            # save_memo — 2종
            ("Write a tool_call JSON to save a memo about {topic}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "save_memo", "arguments": {"title": f"{t} notes", "content": f"Key notes on {t}."}}),
            ("Write a tool_call JSON to save discussion notes with {name} about {topic}. Output JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "save_memo", "arguments": {"title": f"{n} - {t} discussion", "content": f"Discussion with {n} regarding {t}."}}),
        ]
        for pt, out_fn in templates:
            for name in EN_NAMES[:10]:
                for dept in EN_DEPTS[:5]:
                    for topic in EN_TOPICS[:5]:
                        for date in DATES[:5]:
                            for time_ in TIMES[:3]:
                                for loc in KO_LOCS[:3]:
                                    args = out_fn(name, date, topic, time_, loc)
                                    pairs.append((
                                        pt.format(name=name, dept=dept, topic=topic, date=date, time=time_, loc=loc),
                                        args,
                                    ))

    else:  # mixed
        templates = [
            # get_weather — 2종
            ("오늘 {loc} weather를 조회하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": "today"}}),
            ("{date} {loc}의 날씨 forecast JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "get_weather", "arguments": {"location": loc, "date": d}}),
            # add_schedule — 2종
            ("{name}에게 {topic} meeting을 {date}에 schedule하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": f"{n} {t} meeting", "date": d}}),
            ("{date} {time}에 {topic} 일정을 add하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "add_schedule", "arguments": {"title": t, "date": d, "time": ti}}),
            # send_email — 2종
            ("{name}에게 {topic} email을 send하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.replace(' ','')}@company.com", "subject": t, "body": f"안녕하세요 / Hello, regarding {t}."}}),
            ("{topic} update를 {name}에게 메일로 보내는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "send_email", "arguments": {"to": f"{n.replace(' ','')}@company.com", "subject": f"Update: {t}", "body": f"{t} 관련 업데이트입니다."}}),
            # search_contact — 1종
            ("{name}의 contact를 검색하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "search_contact", "arguments": {"name": n}}),
            # summarize_doc — 1종
            ("{topic} document를 short summary로 요약하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "summarize_doc", "arguments": {"document_text": f"{t} document.", "target_length": "short"}}),
            # set_volume — 1종
            ("볼륨을 set하는 tool call JSON (level=70)을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "set_volume", "arguments": {"level": 70}}),
            # toggle_wifi — 1종
            ("Wi-Fi를 disable하는 JSON tool call을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "toggle_wifi", "arguments": {"enabled": False}}),
            # open_file — 1종
            ("{topic} 파일을 open하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "open_file", "arguments": {"path": f"/documents/{t.replace(' ','_')}.txt"}}),
            # save_memo — 1종
            ("{name}과의 {topic} 논의를 memo로 save하는 JSON을 작성하세요. JSON only.",
             lambda n, d, t, ti, loc: {"tool_name": "save_memo", "arguments": {"title": f"{n} {t}", "content": f"{t} 관련 논의 내용입니다."}}),
        ]
        for pt, out_fn in templates:
            for name in KO_NAMES[:10]:
                for dept in KO_DEPTS[:5]:
                    for topic in KO_TOPICS[:8]:
                        for date in DATES[:5]:
                            for time_ in TIMES[:3]:
                                for loc in KO_LOCS[:3]:
                                    args = out_fn(name, date, topic, time_, loc)
                                    pairs.append((
                                        pt.format(name=name, dept=dept, topic=topic, date=date, time=time_, loc=loc),
                                        args,
                                    ))

    return pairs


# ── policy_sensitive ──────────────────────────────────────────────────────
def _make_policy_sensitive_pool(lang: str) -> list[tuple[str, str]]:
    pairs = []

    if lang == "ko":
        q_templates = [
            "{topic} 관련 개인정보를 {name}에게 공유해도 되나요?",
            "{dept}의 {topic} 데이터를 외부에 전달해도 되나요?",
            "{name}이(가) {topic} 시스템에 무단으로 접근하면 어떻게 처리하나요?",
            "{topic} 업무 중 {dept}의 기밀 정보가 유출되면 어떻게 해야 하나요?",
            "{name}의 {topic} 계정을 다른 사람이 사용해도 되나요?",
            "{dept}에서 {topic} 관련 저작권 콘텐츠를 무단 사용하면 어떻게 되나요?",
            "{topic} 관련 업무 자료를 개인 기기에 저장해도 되나요?",
            "{name}이(가) {topic} 비밀번호를 동료에게 알려줘도 되나요?",
        ]
        a_templates = [
            "{topic} 관련 개인정보는 정보 주체의 명시적 동의 없이 {name}에게 공유할 수 없습니다. 개인정보 보호법에 따라 법적 근거가 필요합니다.",
            "{dept}의 {topic} 데이터는 계약 및 정책상 허용된 범위에서만 활용할 수 있습니다. 외부 전달 전 법무팀 검토가 필요합니다.",
            "{name}의 {topic} 시스템 무단 접근은 보안 정책 위반입니다. 즉시 IT보안팀에 보고하고 접근 이력을 보존하세요.",
            "{topic} 관련 기밀 정보 유출 시 즉시 정보보호팀과 법무팀에 신고하고, 관련 증거를 보존해야 합니다.",
            "{topic} 계정 공유는 보안 정책 위반입니다. 각 사용자는 개인 계정을 사용해야 하며, 공유 시 책임을 질 수 있습니다.",
            "{topic} 저작권 콘텐츠 무단 사용은 법적 책임이 따릅니다. 반드시 라이선스 확인 후 법무팀 승인을 받으세요.",
            "{topic} 업무 자료를 개인 기기에 저장하는 것은 정보 유출 위험이 있어 원칙적으로 금지됩니다.",
            "{topic} 비밀번호는 어떤 경우에도 타인에게 공유할 수 없습니다. 접근 권한이 필요하면 IT팀에 공식 신청하세요.",
        ]
        for qt, at in zip(q_templates, a_templates):
            for name in KO_NAMES[:10]:
                for dept in KO_DEPTS[:8]:
                    for topic in KO_TOPICS[:8]:
                        pairs.append((qt.format(name=name, dept=dept, topic=topic),
                                      at.format(name=name, dept=dept, topic=topic)))

    elif lang == "en":
        q_templates = [
            "Can I share {topic} personal data with {name}?",
            "Is it okay to send {dept}'s {topic} data to an external party?",
            "What happens if {name} accesses {topic} systems without authorization?",
            "What should I do if {dept}'s {topic} confidential data is leaked?",
            "Can someone else use {name}'s {topic} account?",
            "What are the consequences if {dept} uses copyrighted {topic} content without permission?",
            "Can I store {topic} work files on my personal device?",
            "Can {name} share their {topic} password with a colleague?",
        ]
        a_templates = [
            "Sharing {topic} personal data with {name} requires explicit consent. Legal basis is required under data protection law.",
            "{dept}'s {topic} data may only be used within policy-permitted scope. Legal review is required before external sharing.",
            "Unauthorized access to {topic} systems by {name} violates security policy. Report to IT Security immediately and preserve access logs.",
            "If {topic} confidential data is leaked, immediately report to the security and legal teams and preserve related evidence.",
            "Sharing {topic} accounts is a security policy violation. Each user must use their own account. Sharing may result in liability.",
            "Unauthorized use of copyrighted {topic} content carries legal liability. Always verify licensing and obtain legal approval.",
            "Storing {topic} work files on personal devices risks data leakage and is generally prohibited.",
            "{topic} passwords must not be shared under any circumstances. Request official access through the IT team if needed.",
        ]
        for qt, at in zip(q_templates, a_templates):
            for name in EN_NAMES[:10]:
                for dept in EN_DEPTS[:8]:
                    for topic in EN_TOPICS[:8]:
                        pairs.append((qt.format(name=name, dept=dept, topic=topic),
                                      at.format(name=name, dept=dept, topic=topic)))

    else:  # mixed
        templates = [
            ("{dept}의 {topic} 데이터를 {name}에게 share해도 돼?",
             "{dept}의 {topic} 데이터는 정책상 허용된 경우에만 {name}에게 공유할 수 있습니다. Legal review required."),
            ("Can I save {name}({dept})'s {topic} files on personal device?",
             "{name}({dept})의 {topic} 파일을 개인 기기에 저장하는 것은 원칙적으로 금지됩니다. This violates security policy."),
            ("{name}({dept})의 {topic} account를 다른 사람이 써도 돼?",
             "{name}({dept})의 {topic} 계정은 본인만 사용해야 합니다. Account sharing is strictly prohibited."),
            ("{dept}의 {topic} 정보를 {name} 통해 external에 보내도 돼?",
             "{dept}의 {topic} 정보 외부 전달은 법무팀 검토가 필요합니다. Consult Legal before sharing via {name}."),
            ("Is it okay to share {dept}'s {topic} data with {name}?",
             "{dept}의 {topic} 데이터는 {name}에게 공유하기 전 반드시 승인이 필요합니다. Approval required."),
            ("{name}이(가) {dept} {topic} system에 무단 접근하면?",
             "{name}의 {dept} {topic} 시스템 무단 접근은 보안 정책 위반입니다. Report to IT Security immediately."),
            ("Can {name} use {dept}'s {topic} credentials for another project?",
             "{name}이(가) {dept}의 {topic} 자격 증명을 다른 프로젝트에 사용하는 것은 금지됩니다. This is a policy violation."),
            ("{dept}에서 {topic} 관련 {name}의 personal email로 자료 전송 가능?",
             "{dept}의 {topic} 자료를 {name}의 개인 이메일로 전송하는 것은 보안 정책 위반입니다. Use official channels only."),
        ]
        for pt, at in templates:
            for name in KO_NAMES[:10]:
                for dept in KO_DEPTS[:8]:
                    for topic in KO_TOPICS[:8]:
                        pairs.append((pt.format(name=name, dept=dept, topic=topic),
                                      at.format(name=name, dept=dept, topic=topic)))

    return pairs


# ── retrieval_transform ───────────────────────────────────────────────────
def _make_retrieval_transform_pool(lang: str) -> list[tuple[str, str]]:
    pairs = []
    import datetime

    if lang == "ko":
        templates = [
            ("다음에서 이름만 추출하세요: {name1}({age1}세), {name2}({age2}세), {name3}({age3}세)",
             "{name1}, {name2}, {name3}"),
            ("다음을 JSON으로 변환하세요: 이름: {name1}, 부서: {dept}, 직급: {role}",
             '{{"이름": "{name1}", "부서": "{dept}", "직급": "{role}"}}'),
            ("{num1}, {num2}, {num3}의 평균을 계산하세요.",
             "{avg}"),
            ("{name1}, {name2}, {name3}를 가나다순으로 정렬하세요.",
             "{sorted_names}"),
            ("다음에서 날짜만 추출하세요: {name1}의 {topic} 마감일은 {date}입니다.",
             "{date}"),
            ("다음에서 부서명만 추출하세요: {name1}({dept}) {name2}({dept2})",
             "{dept}, {dept2}"),
            ("{date}를 한국어 날짜 형식으로 변환하세요.",
             "{date_ko}"),
            ("다음 이메일에서 도메인만 추출하세요: {name1}@{domain}",
             "{domain}"),
        ]
        roles = ["과장", "차장", "부장", "대리", "사원", "팀장", "이사", "상무"]
        for name1, name2, name3 in itertools.islice(itertools.combinations(KO_NAMES, 3), 50):
            for dept, dept2 in itertools.islice(itertools.combinations(KO_DEPTS[:8], 2), 20):
                for date in DATES[:5]:
                    age1, age2, age3 = random.randint(25, 45), random.randint(25, 45), random.randint(25, 45)
                    num1, num2, num3 = random.randint(10, 90), random.randint(10, 90), random.randint(10, 90)
                    avg = round((num1 + num2 + num3) / 3, 1)
                    sorted_ns = ", ".join(sorted([name1, name2, name3]))
                    date_ko = date.replace("-", "년 ", 1).replace("-", "월 ") + "일"
                    domain = "company.com"
                    role = random.choice(roles)
                    topic = random.choice(KO_TOPICS[:10])
                    ctx = dict(name1=name1, name2=name2, name3=name3,
                               age1=age1, age2=age2, age3=age3,
                               dept=dept, dept2=dept2, date=date,
                               num1=num1, num2=num2, num3=num3,
                               avg=avg, sorted_names=sorted_ns,
                               date_ko=date_ko, domain=domain,
                               role=role, topic=topic)
                    for pt_t, ans_t in templates:
                        try:
                            pairs.append((pt_t.format(**ctx), ans_t.format(**ctx)))
                        except Exception:
                            pass

    elif lang == "en":
        templates = [
            ("Extract only the names from: {name1} ({age1}), {name2} ({age2}), {name3} ({age3})",
             "{name1}, {name2}, {name3}"),
            ("Convert to JSON: Name: {name1}, Department: {dept}, Role: {role}",
             '{{"Name": "{name1}", "Department": "{dept}", "Role": "{role}"}}'),
            ("Calculate the average of {num1}, {num2}, {num3}.",
             "{avg}"),
            ("Sort alphabetically: {name1}, {name2}, {name3}",
             "{sorted_names}"),
            ("Extract the date from: {name1}'s {topic} deadline is {date}.",
             "{date}"),
            ("Extract department names from: {name1}({dept}) {name2}({dept2})",
             "{dept}, {dept2}"),
            ("Format {date} as US date format.",
             "{date_us}"),
            ("Extract the domain from: {name1}@{domain}",
             "{domain}"),
        ]
        roles = ["Manager", "Director", "Lead", "Senior", "Junior", "VP", "Analyst", "Associate"]
        for name1, name2, name3 in itertools.islice(itertools.combinations(EN_NAMES, 3), 50):
            for dept, dept2 in itertools.islice(itertools.combinations(EN_DEPTS[:8], 2), 20):
                for date in DATES[:5]:
                    age1, age2, age3 = random.randint(25, 45), random.randint(25, 45), random.randint(25, 45)
                    num1, num2, num3 = random.randint(10, 90), random.randint(10, 90), random.randint(10, 90)
                    avg = round((num1 + num2 + num3) / 3, 1)
                    sorted_ns = ", ".join(sorted([name1, name2, name3]))
                    date_us = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
                    domain = "company.com"
                    role = random.choice(roles)
                    topic = random.choice(EN_TOPICS[:10])
                    ctx = dict(name1=name1, name2=name2, name3=name3,
                               age1=age1, age2=age2, age3=age3,
                               dept=dept, dept2=dept2, date=date,
                               num1=num1, num2=num2, num3=num3,
                               avg=avg, sorted_names=sorted_ns,
                               date_us=date_us, domain=domain,
                               role=role, topic=topic)
                    for pt_t, ans_t in templates:
                        try:
                            pairs.append((pt_t.format(**ctx), ans_t.format(**ctx)))
                        except Exception:
                            pass

    else:  # mixed
        templates = [
            ("{name1}({age1}세)와 {name2}({age2}세)에서 extract the ages.", "{age1}, {age2}"),
            ("{name1}의 {dept}를 English로 변환하세요.", "{dept_en}"),
            ("Extract names: {name1} works in {dept}, {name2} works in {dept2}.", "{name1}, {name2}"),
            ("{num1}, {num2}, {num3}의 average를 계산하세요.", "{avg}"),
        ]
        dept_en_map = dict(zip(KO_DEPTS[:8], EN_DEPTS[:8]))
        for name1, name2 in itertools.islice(itertools.combinations(KO_NAMES, 2), 80):
            for dept, dept2 in itertools.islice(itertools.combinations(KO_DEPTS[:8], 2), 20):
                for _ in range(3):
                    age1, age2 = random.randint(25, 45), random.randint(25, 45)
                    num1, num2, num3 = random.randint(10, 90), random.randint(10, 90), random.randint(10, 90)
                    avg = round((num1 + num2 + num3) / 3, 1)
                    dept_en = dept_en_map.get(dept, dept)
                    ctx = dict(name1=name1, name2=name2, age1=age1, age2=age2,
                               dept=dept, dept2=dept2, dept_en=dept_en,
                               num1=num1, num2=num2, num3=num3, avg=avg)
                    for pt_t, ans_t in templates:
                        try:
                            pairs.append((pt_t.format(**ctx), ans_t.format(**ctx)))
                        except Exception:
                            pass

    return pairs


# ═══════════════════════════════════════════════════════════════
# 레코드 변환 및 검증
# ═══════════════════════════════════════════════════════════════

def build_record(function: str, lang: str, inp: str, out: Any, idx: int) -> dict:
    out_str = json.dumps(out, ensure_ascii=False) if isinstance(out, dict) else str(out)
    return {
        "id": f"{function}_{lang}_{idx:05d}",
        "function": function,
        "lang": lang,
        "prompt": inp,
        "completion": out_str,
        "prompt_digest_sha256": sha256_text(inp),
        "output_digest_sha256": sha256_text(out_str),
        "format": "qwen2.5_chat",
        "split": random.choices(["train", "val", "test"], weights=[0.8, 0.1, 0.1])[0],
    }


def validate_record(r: dict) -> bool:
    req = ["id", "function", "lang", "prompt", "completion",
           "prompt_digest_sha256", "output_digest_sha256", "format", "split"]
    if not all(k in r for k in req):
        return False
    if not str(r["prompt"]).strip():
        return False
    if not str(r["completion"]).strip():
        return False
    if len(r["prompt_digest_sha256"]) != 64 or len(r["output_digest_sha256"]) != 64:
        return False
    if r["split"] not in ("train", "val", "test"):
        return False
    if r["format"] != "qwen2.5_chat":
        return False
    return True


def generate_function_data(function: str, lang: str, count: int, schema: dict) -> list[dict]:
    pool_fn = {
        "dialogue":            _make_dialogue_pool,
        "summarize":           _make_summarize_pool,
        "rewrite":             _make_rewrite_pool,
        "policy_sensitive":    _make_policy_sensitive_pool,
        "retrieval_transform": _make_retrieval_transform_pool,
    }

    if function == "tool_call":
        raw_pool = _make_tool_call_pool(lang, schema)
    else:
        raw_pool = pool_fn[function](lang)

    # unique 필터
    seen: set[str] = set()
    unique_pool: list[tuple[Any, Any]] = []
    for inp, out in raw_pool:
        key = sha256_text(str(inp))
        if key not in seen:
            seen.add(key)
            unique_pool.append((inp, out))

    # unique_ratio 사전 검증
    unique_ratio = len(unique_pool) / count if count > 0 else 0.0
    if unique_ratio < UNIQUE_RATIO_MIN:
        raise RuntimeError(
            f"UNIQUE_RATIO_TOO_LOW:{function}:{lang}:{unique_ratio:.4f} "
            f"(pool={len(unique_pool)}, count={count}, required>={UNIQUE_RATIO_MIN})\n"
            f"→ 템플릿 풀 확충 또는 count 축소 필요"
        )

    random.shuffle(unique_pool)
    sample = unique_pool[:count]

    records = []
    for idx, (inp, out) in enumerate(sample):
        r = build_record(function, lang, inp, out, idx)
        if validate_record(r):
            records.append(r)

    return records


# ═══════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--functions", nargs="+", default=["all"])
    parser.add_argument("--lang",      nargs="+", default=["ko", "en", "mixed"])
    parser.add_argument("--count",     type=int,  default=500)
    parser.add_argument("--out",       type=str,  default="data/synthetic/")
    parser.add_argument("--seed",      type=int,  default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    funcs   = FUNCTIONS if "all" in args.functions else args.functions
    langs   = args.lang
    count   = args.count
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    schema = load_tool_schema()

    stats: dict = {}
    total_generated = 0
    total_valid = 0
    all_ok = True

    for func in funcs:
        stats[func] = {}
        func_records = []
        for lang in langs:
            try:
                records = generate_function_data(func, lang, count, schema)
            except RuntimeError as e:
                print(f"  ERROR [{func}/{lang}]: {e}", file=sys.stderr)
                sys.exit(1)

            stats[func][lang] = {
                "valid":        len(records),
                "requested":    count,
                "unique_ratio": round(len(records) / count, 4) if count else 0,
            }
            func_records.extend(records)
            total_generated += len(records)
            total_valid     += len(records)

        out_path = out_dir / f"{func}_synthetic.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for r in func_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  {func}: {len(func_records)}건 → {out_path}")

    # B6: count × len(langs) 기준 판정
    for func in funcs:
        func_total = sum(stats[func].get(l, {}).get("valid", 0) for l in langs)
        if func_total < count * len(langs):
            print(f"  WARN: {func} {func_total}건 < {count * len(langs)}건", file=sys.stderr)
            all_ok = False

    summary = {
        "SYNTHETIC_DATA_OK": 1 if all_ok else 0,
        "total_valid":       total_valid,
        "count_per_lang":    count,
        "functions":         funcs,
        "languages":         langs,
        "stats":             stats,
    }
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/synthetic_data_stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nSYNTHETIC_DATA_OK={summary['SYNTHETIC_DATA_OK']}")
    print(f"total_valid={total_valid}")
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
