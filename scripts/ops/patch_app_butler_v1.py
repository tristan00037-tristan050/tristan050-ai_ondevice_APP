#!/usr/bin/env python3
"""
app.py Butler 패치: 현재 레포 구조(사이드바에 Model Test 포함) 기준.
앵커 불일치 시 [BLOCK]으로 중단.
"""
from pathlib import Path
import re
import sys
import textwrap

p = Path("ondevice-pr-timeline/app.py")
if not p.exists():
    raise SystemExit("[BLOCK] ondevice-pr-timeline/app.py not found")
s = p.read_text(encoding="utf-8")

# 1) MODULES를 본체/운영판 2묶음으로 확장
new_modules = textwrap.dedent('''\
# --- Platform Modules (SSOT-aligned) ---
MODULES = [
    {"key": "butler_qa_analysis", "group": "product", "name": "버틀러 질문/분석", "status": "LOCKED", "why": "제품 본체 v0", "dod": "질문 입력 + 결과 3블록 + Mock/Live 상태 표시"},
    {"key": "butler_draft_review", "group": "product", "name": "버틀러 초안/검토", "status": "LOCKED", "why": "제품 본체 v0", "dod": "초안/검토 요청 + 결과 3블록 + 승인 전 상태 표시"},
    {"key": "butler_file_edit", "group": "product", "name": "버틀러 파일 수정", "status": "LOCKED", "why": "에이전틱 본체 확장", "dod": "대상 파일 지정 + 수정 계획 + 승인/반영 기록"},
    {"key": "butler_project_manage", "group": "product", "name": "버틀러 프로젝트 관리", "status": "LOCKED", "why": "에이전틱 본체 확장", "dod": "작업 계획/상태 변경/실행 기록 표시"},

    {"key": "doc_search", "group": "ops", "name": "문서 검색/요약", "status": "LOCKED", "why": "MVP 시나리오 #1", "dod": "DOC_SEARCH_* 4키(allow/block/meta_only/join)"},
    {"key": "write_approve_export", "group": "ops", "name": "초안 + 승인 + 반출", "status": "LOCKED", "why": "MVP 시나리오 #2 + Export 2단계", "dod": "WRITE_APPROVE_* 4키 + EXPORT_APPROVE_*"},
    {"key": "helpdesk_ticket", "group": "ops", "name": "헬프데스크 티켓", "status": "LOCKED", "why": "MVP 시나리오 #3", "dod": "HELPDESK_* 4키"},
    {"key": "ssot_updates", "group": "ops", "name": "SSOT 변경 기록", "status": "READY", "why": "방향 흔들림 0", "dod": "SSOT 변경 시 CHANGELOG+ADR 강제"},
    {"key": "decisions", "group": "ops", "name": "결정 기록(ADR)", "status": "READY", "why": "방향 변경의 단일 기록", "dod": "ADR 제목/날짜/상태 표시"},
    {"key": "ai_perf", "group": "ops", "name": "AI 성능(accuracy/latency/ram)", "status": "READY", "why": "성능 변화 가시화", "dod": "eval_results 최신 2개 비교"},
    {"key": "raw0_enforce", "group": "ops", "name": "원문0 전수 봉인(로그/예외/리포트)", "status": "LOCKED", "why": "추가 고정 #2", "dod": "NO_RAW_* 게이트 + 전수 스캔"},
    {"key": "pack_bypass", "group": "ops", "name": "업무팩 우회 봉인", "status": "LOCKED", "why": "추가 고정 #1", "dod": "PACK_* 우회 탐지/차단"},
    {"key": "mvp_package", "group": "ops", "name": "상품성 패키지(3시나리오+운영콘솔)", "status": "LOCKED", "why": "추가 고정 #3", "dod": "3시나리오 READY + 운영콘솔 v0"},
]
# --- end modules ---
''')

pattern_modules = r'# --- Platform Modules \(SSOT-aligned\) ---\nMODULES = \[\n.*?\n\]\n# --- end modules ---'
new, n = re.subn(pattern_modules, new_modules, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit("[BLOCK] MODULES block anchor not found")
s = new

# 2) 좌측 메뉴에 Butler 추가 (현재 구조: Model Test 포함 7개 링크)
old_nav = """      <a href="/" class="{{ 'active' if active == 'dashboard' else '' }}">Dashboard</a>
      <a href="/timeline" class="{{ 'active' if active == 'timeline' else '' }}">Timeline</a>
      <a href="/modules" class="{{ 'active' if active == 'modules' else '' }}">Modules</a>
      <a href="/model-test" class="{{ 'active' if active == 'model-test' else '' }}">Model Test</a>
      <a href="/roadmap" class="{{ 'active' if active == 'roadmap' else '' }}">Roadmap</a>
      <a href="/updates" class="{{ 'active' if active == 'updates' else '' }}">Updates</a>
      <a href="/decisions" class="{{ 'active' if active == 'decisions' else '' }}">Decisions</a>
"""

new_nav = """      <a href="/" class="{{ 'active' if active == 'dashboard' else '' }}">Dashboard</a>
      <a href="/butler" class="{{ 'active' if active == 'butler' else '' }}">Butler</a>
      <a href="/timeline" class="{{ 'active' if active == 'timeline' else '' }}">Timeline</a>
      <a href="/modules" class="{{ 'active' if active == 'modules' else '' }}">Modules</a>
      <a href="/model-test" class="{{ 'active' if active == 'model-test' else '' }}">Model Test</a>
      <a href="/roadmap" class="{{ 'active' if active == 'roadmap' else '' }}">Roadmap</a>
      <a href="/updates" class="{{ 'active' if active == 'updates' else '' }}">Updates</a>
      <a href="/decisions" class="{{ 'active' if active == 'decisions' else '' }}">Decisions</a>
"""

if old_nav not in s:
    raise SystemExit("[BLOCK] sidebar nav anchor not found")
s = s.replace(old_nav, new_nav, 1)

# 3) Dashboard 상단에 제품 정의 카드 추가 (f-string 유지: 기존 첫 카드 앞에 삽입, 들여쓰기 4칸 유지)
old_dashboard_start = '    html = refresh_banner + f"""\n    <div class="card">\n      <h3>Dashboard</h3>'
new_dashboard_start = '''    html = refresh_banner + f"""
    <div class="card">
      <h3>제품 정의</h3>
      <div class="hint">
        우리 서비스의 본체는 직원 및 회사 내 허가된 모든 사람과 부서들이 실제로 질문·분석·초안·검토를 요청했을 때
        컴퓨터 내 AI가 작동하는 버틀러 기능이며, 버틀러는 질문·답변에 그치지 않고 단순 응답을 넘어
        실제 파일 수정과 프로젝트를 관리하는 에이전틱(Agentic) 도구입니다.
      </div>
      <div class="hint">
        운영 콘솔은 버틀러를 대체하지 않으며, 버틀러 본체의 개발 상태·품질·방향·변경 이력·성능을 관리하고 확인하는 목적에 한정합니다.
      </div>
      <div style="margin-top:10px;">
        <a href="/butler" class="pill">Butler 보기</a>
        <a href="/modules" class="pill">Modules 보기</a>
      </div>
    </div>

    <div class="card">
      <h3>Dashboard</h3>'''

if old_dashboard_start not in s:
    raise SystemExit("[BLOCK] dashboard html anchor not found")
s = s.replace(old_dashboard_start, new_dashboard_start, 1)

# 4) Modules 페이지 전체를 본체/운영판 2묶음으로 교체
modules_func_pattern = r'@app\.get\("/modules"\)\ndef modules_page\(\):\n.*?\n\ndef _run_verify_background\(\):'
new_modules_func = textwrap.dedent('''\
@app.get("/modules")
def modules_page():
    groups = [
        ("product", "버틀러 본체 영역", "직원 및 허가된 사용자/부서가 실제로 쓰는 제품 본체입니다. 실구현 근거가 부족한 기능은 LOCKED/PARTIAL로 정직하게 표시합니다."),
        ("ops", "운영판 영역", "개발 방향/변경/상태/성능/진단을 보는 관리판입니다."),
    ]

    sections = ""
    for group_key, title, desc in groups:
        cards = ""
        for m in [x for x in MODULES if x.get("group", "ops") == group_key]:
            status = get_effective_module_status(m["key"])
            color = "#a9b6d6"
            if status == "READY":
                color = "#3ddc97"
            elif status == "PARTIAL":
                color = "#ffd166"
            elif status == "LOCKED":
                color = "#ff6b6b"
            name = _html_escape(m["name"])
            why = _html_escape(m["why"])
            dod = _html_escape(m["dod"])
            cards += f"""
            <div class="card" style="margin:10px 0;">
              <div style="display:flex; justify-content:space-between; gap:10px; align-items:center;">
                <div style="font-weight:900;">{name}</div>
                <span class="pill" style="border-color:rgba(255,255,255,.08); color:{color};">{status}</span>
              </div>
              <div class="hint" style="margin-top:8px;"><b>의미</b>: {why}</div>
              <div class="hint"><b>PASS 조건(DoD)</b>: {dod}</div>
            </div>
            """
        sections += f"""
        <div class="card" style="margin-top:12px;">
          <h3>{_html_escape(title)}</h3>
          <div class="hint">{_html_escape(desc)}</div>
        </div>
        {cards}
        """

    html = """
    <div class="card">
      <h3>Modules</h3>
      <div class="hint">
        제품 본체는 Butler이고, 콘솔은 Butler의 개발·운영 상태를 보여주는 운영판입니다.
        본체/운영판을 분리 표시하며, 없는 기능을 있는 것처럼 보이지 않게 LOCKED/PARTIAL/READY로 정직하게 표시합니다.
      </div>
      <div style="margin-top:10px;">
        <a href="/api/refresh?redirect=/modules" class="pill" style="text-decoration:none;">🔄 상태 갱신(verify 실행)</a>
      </div>
    </div>
    """
    html = _refresh_banner_html() + html + sections
    return render("modules", "Modules", "본체(Butler)와 운영판을 분리해 개발 상태를 확인합니다.", html)


def _run_verify_background():
''')

new, n = re.subn(modules_func_pattern, new_modules_func, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit("[BLOCK] modules_page function anchor not found")
s = new

# 5) /butler 화면 추가
butler_block = textwrap.dedent('''\

@app.route("/butler", methods=["GET", "POST"])
def butler_page():
    prompt = (request.values.get("prompt") or "").strip()
    work_mode = (request.values.get("work_mode") or "qa_analysis").strip()
    runtime = (request.values.get("runtime") or "MOCK").strip().upper()

    product_keys = [
        "butler_qa_analysis",
        "butler_draft_review",
        "butler_file_edit",
        "butler_project_manage",
    ]
    product_modules = [m for m in MODULES if m["key"] in product_keys]

    mode_labels = {
        "qa_analysis": "질문/분석",
        "draft_review": "초안/검토",
        "file_edit": "파일 수정",
        "project_manage": "프로젝트 관리",
    }

    def _status_color(st: str) -> str:
        if st == "READY":
            return "#3ddc97"
        if st == "PARTIAL":
            return "#ffd166"
        return "#ff6b6b"

    cards = ""
    for m in product_modules:
        st = get_effective_module_status(m["key"])
        cards += f"""
        <div class="card" style="margin:10px 0;">
          <div style="display:flex; justify-content:space-between; gap:10px; align-items:center;">
            <div style="font-weight:900;">{_html_escape(m["name"])}</div>
            <span class="pill" style="color:{_status_color(st)};">{st}</span>
          </div>
          <div class="hint" style="margin-top:8px;"><b>의미</b>: {_html_escape(m["why"])}</div>
          <div class="hint"><b>PASS 조건(DoD)</b>: {_html_escape(m["dod"])}</div>
        </div>
        """

    result_html = ""
    if prompt:
        safe_prompt = _html_escape(prompt)
        mode_name = _html_escape(mode_labels.get(work_mode, work_mode))
        if runtime == "MOCK":
            result_html = f"""
            <div class="card" style="margin-top:12px;">
              <h3>실행 결과 (MOCK)</h3>
              <div class="hint">이 화면은 제품 본체를 미리 체감하고, 기능이 붙을 때마다 업그레이드 상태를 확인하기 위한 안전한 Mock 결과입니다.</div>
              <div class="hint" style="margin-top:10px;"><b>요청</b>: {safe_prompt}</div>
              <div class="hint"><b>업무 모드</b>: {mode_name}</div>
              <div class="card" style="margin-top:12px;">
                <div style="font-weight:900;">핵심 포인트</div>
                <div class="hint">현재는 Mock 모드입니다. 입력한 요청을 Butler 본체 화면에서 수용할 수 있도록 골격이 준비되었습니다.</div>
              </div>
              <div class="card" style="margin-top:12px;">
                <div style="font-weight:900;">결정</div>
                <div class="hint">실기능 연결 전까지는 LOCKED/PARTIAL 상태를 유지하고, 기능이 붙는 즉시 이 영역을 Live 결과로 교체합니다.</div>
              </div>
              <div class="card" style="margin-top:12px;">
                <div style="font-weight:900;">다음 행동</div>
                <div class="hint">관련 기능 구현 후 Mock → Live 전환, 실행 이력 저장, 승인/반영 흐름 연결이 필요합니다.</div>
              </div>
            </div>
            """
        else:
            result_html = f"""
            <div class="card" style="margin-top:12px; border-left:4px solid #ff6b6b;">
              <h3>실행 결과 (LIVE 요청)</h3>
              <div class="hint"><b>요청</b>: {safe_prompt}</div>
              <div class="hint"><b>업무 모드</b>: {mode_name}</div>
              <div class="hint" style="color:#ff6b6b;">현재 Live 버틀러 실행은 실구현 근거가 부족하므로 LOCKED 상태입니다. 화면은 미리 열어두되, 없는 기능을 있는 것처럼 실행하지 않습니다.</div>
            </div>
            """

    html = f"""
    <div class="card">
      <h3>Butler</h3>
      <div class="hint">
        우리 서비스의 본체는 Butler입니다. Butler는 단순 질의응답 도구가 아니라,
        질문·분석·초안·검토·수정·관리까지 수행하는 에이전틱 도구입니다.
      </div>
      <form method="get" action="/butler" style="margin-top:12px;">
        <div style="display:grid; gap:10px;">
          <label class="hint">업무 모드</label>
          <select name="work_mode" style="padding:10px; border-radius:10px; background:#0f172a; color:#e8eefc; border:1px solid rgba(255,255,255,.12);">
            <option value="qa_analysis" {"selected" if work_mode == "qa_analysis" else ""}>질문/분석</option>
            <option value="draft_review" {"selected" if work_mode == "draft_review" else ""}>초안/검토</option>
            <option value="file_edit" {"selected" if work_mode == "file_edit" else ""}>파일 수정</option>
            <option value="project_manage" {"selected" if work_mode == "project_manage" else ""}>프로젝트 관리</option>
          </select>

          <label class="hint">실행 모드</label>
          <select name="runtime" style="padding:10px; border-radius:10px; background:#0f172a; color:#e8eefc; border:1px solid rgba(255,255,255,.12);">
            <option value="MOCK" {"selected" if runtime == "MOCK" else ""}>MOCK</option>
            <option value="LIVE" {"selected" if runtime == "LIVE" else ""}>LIVE(현재 LOCKED)</option>
          </select>

          <label class="hint">요청 입력</label>
          <textarea name="prompt" rows="6" style="padding:12px; border-radius:12px; background:#0f172a; color:#e8eefc; border:1px solid rgba(255,255,255,.12);" placeholder="예: 이 문서 핵심만 요약해줘 / 이 변경사항 위험도 검토해줘 / 이 파일 수정 계획을 세워줘">{_html_escape(prompt)}</textarea>

          <div>
            <button type="submit" class="pill" style="cursor:pointer;">실행</button>
            <a href="/modules" class="pill">Modules 보기</a>
          </div>
        </div>
      </form>
    </div>

    <div class="card" style="margin-top:12px;">
      <h3>Butler 본체 상태</h3>
      <div class="hint">실구현 근거가 충분하지 않은 기능은 LOCKED/PARTIAL로만 표시합니다.</div>
    </div>

    {cards}
    {result_html}
    """
    return render("butler", "Butler", "제품 본체(Butler) 화면: 질문·분석·초안·검토·수정·관리", html)
''')

roadmap_anchor = '\n# Roadmap: Phase 1 체크리스트 (SSOT v1.0 기준)\n'
if roadmap_anchor not in s:
    raise SystemExit("[BLOCK] roadmap anchor not found")
s = s.replace(roadmap_anchor, butler_block + roadmap_anchor, 1)

p.write_text(s, encoding="utf-8")
print("OK: app.py patched")
