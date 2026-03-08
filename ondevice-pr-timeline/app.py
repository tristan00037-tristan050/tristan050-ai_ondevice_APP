import os, re, time, json, subprocess, shlex, threading
from datetime import datetime, date
from pathlib import Path
from glob import glob
import requests
import jwt
from flask import Flask, jsonify, redirect, render_template_string, request

# Paths (앱/레포 기준)
_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
_VERIFY_CACHE_PATH = _APP_ROOT / ".local" / "verify_cache.json"
_SSOT_DOD_KEYS_PATH = _REPO_ROOT / "docs" / "ssot" / "MODULE_DOD_KEYS_V1.json"


def _load_module_dod_keys():
    """MODULE_DOD_KEYS: docs/ssot/MODULE_DOD_KEYS_V1.json (SSOT). 없으면 기본값."""
    default = {
        "doc_search": ["DEMO_DOC_SEARCH_ALLOW_OK", "DEMO_DOC_SEARCH_BLOCK_OK", "DEMO_DOC_SEARCH_META_ONLY_OK", "DEMO_DOC_SEARCH_REQUEST_ID_JOIN_OK"],
        "write_approve_export": ["DEMO_WRITE_APPROVE_ALLOW_OK", "DEMO_WRITE_APPROVE_BLOCK_OK", "DEMO_WRITE_APPROVE_META_ONLY_OK", "DEMO_WRITE_APPROVE_REQUEST_ID_JOIN_OK"],
        "helpdesk_ticket": ["DEMO_HELPDESK_ALLOW_OK", "DEMO_HELPDESK_BLOCK_OK", "DEMO_HELPDESK_META_ONLY_OK", "DEMO_HELPDESK_REQUEST_ID_JOIN_OK"],
        "ssot_updates": ["SSOT_CHANGE_DISCIPLINE_V1_OK"],
        "decisions": [],
        "ai_perf": [],
        "raw0_enforce": ["NO_RAW_IN_LOGS_POLICY_V1_OK", "NO_RAW_IN_REPORTS_SCAN_V1_OK"],
        "pack_bypass": ["PACK_CORE_BYPASS_POLICY_V1_OK", "PACK_FORBIDDEN_IMPORT_BLOCK_V1_OK", "PACK_MANIFEST_SCHEMA_LOCK_V1_OK"],
        "mvp_package": [],
    }
    try:
        if _SSOT_DOD_KEYS_PATH.exists():
            data = json.loads(_SSOT_DOD_KEYS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return default


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


# 모듈별 DoD 키: docs/ssot/MODULE_DOD_KEYS_V1.json (SSOT). 변경 시 CHANGELOG+ADR 적용.
MODULE_DOD_KEYS = _load_module_dod_keys()

_verify_cache = {"output": {}, "status": {}, "ts": None, "error": None, "running": False, "result": None, "result_ts": None, "failed_guard": None}


def _load_verify_cache():
    """저장된 갱신 결과만 로드(키/값·결과만, 원문 미저장)."""
    try:
        if _VERIFY_CACHE_PATH.exists():
            data = json.loads(_VERIFY_CACHE_PATH.read_text(encoding="utf-8"))
            if data.get("result_ts"):
                _verify_cache["result_ts"] = data["result_ts"]
            if data.get("result") is not None:
                _verify_cache["result"] = data["result"]
            if data.get("failed_guard") is not None:
                _verify_cache["failed_guard"] = data["failed_guard"]
            if isinstance(data.get("status"), dict):
                _verify_cache["status"] = data["status"]
    except Exception:
        pass


def _save_verify_cache():
    """갱신 결과만 저장(result_ts/result/failed_guard/status). 원문·stderr 미저장."""
    try:
        _APP_ROOT.joinpath(".local").mkdir(parents=True, exist_ok=True)
        payload = {
            "result_ts": _verify_cache.get("result_ts"),
            "result": _verify_cache.get("result"),
            "failed_guard": _verify_cache.get("failed_guard"),
            "status": _verify_cache.get("status") or {},
        }
        _VERIFY_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass


_load_verify_cache()


def _run_verify_and_parse():
    """레포 루트에서 verify 실행 후 KEY=VALUE 라인만 파싱. 원문·stderr 저장 안 함."""
    script = _REPO_ROOT / "scripts" / "verify" / "verify_repo_contracts.sh"
    if not script.exists():
        _verify_cache["error"] = "verify_repo_contracts.sh not found"
        _verify_cache["result"] = "FAIL"
        _verify_cache["result_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _verify_cache["failed_guard"] = "verify_repo_contracts.sh not found"
        _save_verify_cache()
        return
    try:
        r = subprocess.run(
            ["bash", str(script)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        kv = {}
        for line in out.splitlines():
            m = re.match(r"^([A-Za-z0-9_]+)=(\d+)$", line.strip())
            if m:
                kv[m.group(1)] = m.group(2)
            m = re.match(r"^([A-Za-z0-9_]+)_SKIPPED=(\d+)$", line.strip())
            if m:
                kv[m.group(1) + "_SKIPPED"] = m.group(2)
        _verify_cache["output"] = kv
        _verify_cache["error"] = None
        _verify_cache["ts"] = time.time()
        _verify_cache["result_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        failed_line = None
        for line in out.splitlines():
            s = line.strip()
            if "REPO_CONTRACTS_FAILED_GUARD=" in s or "ERROR_CODE=" in s:
                failed_line = s[:200]
                break
        if r.returncode != 0 or failed_line:
            _verify_cache["result"] = "FAIL"
            _verify_cache["failed_guard"] = failed_line or f"exit code {r.returncode}"
        else:
            _verify_cache["result"] = "OK"
            _verify_cache["failed_guard"] = None
        # 각 모듈 status 계산
        for m in MODULES:
            key = m["key"]
            default = m.get("status", "LOCKED")
            if key == "mvp_package":
                s1 = _compute_module_status("doc_search", kv)
                s2 = _compute_module_status("write_approve_export", kv)
                s3 = _compute_module_status("helpdesk_ticket", kv)
                if s1 == s2 == s3 == "READY":
                    _verify_cache["status"][key] = "READY"
                elif s1 == "READY" or s2 == "READY" or s3 == "READY":
                    _verify_cache["status"][key] = "PARTIAL"
                else:
                    _verify_cache["status"][key] = "LOCKED"
                continue
            if key in ("decisions", "ai_perf") and not MODULE_DOD_KEYS.get(key):
                _verify_cache["status"][key] = default
                continue
            _verify_cache["status"][key] = _compute_module_status(key, kv) or default
        _save_verify_cache()
    except subprocess.TimeoutExpired:
        _verify_cache["error"] = "verify timeout (180s)"
        _verify_cache["result"] = "FAIL"
        _verify_cache["result_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _verify_cache["failed_guard"] = "verify timeout (180s)"
        _save_verify_cache()
    except Exception as e:
        _verify_cache["error"] = str(e)
        _verify_cache["result"] = "FAIL"
        _verify_cache["result_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _verify_cache["failed_guard"] = str(e)[:200]
        _save_verify_cache()


def _compute_module_status(module_key: str, kv: dict) -> str:
    keys = MODULE_DOD_KEYS.get(module_key, [])
    if not keys:
        return None
    any_skipped = any(kv.get(k.replace("_OK", "_SKIPPED")) == "1" for k in keys)
    all_ok = all(kv.get(k) == "1" for k in keys)
    if all_ok:
        return "READY"
    if any_skipped or any(kv.get(k) == "1" for k in keys):
        return "PARTIAL"
    return "LOCKED"


def get_effective_module_status(module_key: str) -> str:
    """캐시에 있으면 verify 기반, 없으면 MODULES 기본값."""
    if _verify_cache["status"]:
        return _verify_cache["status"].get(module_key) or next((m["status"] for m in MODULES if m["key"] == module_key), "LOCKED")
    return next((m["status"] for m in MODULES if m["key"] == module_key), "LOCKED")


# 실패 가드 코드 → 사람이 읽기 쉬운 한 줄 설명(고정)
FAILED_GUARD_HINTS = {
    "SSOT_CHANGED_WITHOUT_CHANGELOG": "SSOT만 바꾸고 변경기록(CHANGELOG)이 없어 차단",
    "SSOT_CHANGED_WITHOUT_ADR": "방향 변경 결정을 ADR로 남기지 않아 차단",
}


def _failed_guard_hint(raw: str) -> str:
    """실패 가드 원문을 인간 친화적 한 줄로 변환."""
    if not raw or not isinstance(raw, str):
        return raw or ""
    s = raw.strip()[:200]
    for code, hint in FAILED_GUARD_HINTS.items():
        if code in s:
            return hint
    if "REPO_CONTRACTS_FAILED_GUARD=" in s:
        part = s.split("REPO_CONTRACTS_FAILED_GUARD=", 1)[-1].strip()
        return f"레포 계약 가드 실패: {part[:80]}"
    if "ERROR_CODE=" in s:
        part = s.split("ERROR_CODE=", 1)[-1].strip()
        return f"가드 오류: {part[:80]}"
    return s


def _refresh_banner_html():
    """Dashboard/Modules 상단에 쓸 갱신 결과/실행 중 배지 HTML."""
    if _verify_cache.get("running"):
        return '<div class="card" style="margin-bottom:12px; border-color:rgba(255,209,102,.4);"><span class="pill" style="color:#ffd166;">⏳ 상태 갱신 실행 중… (1~2분 소요)</span></div>'
    ts = _verify_cache.get("result_ts")
    result = _verify_cache.get("result")
    failed = _verify_cache.get("failed_guard")
    if not ts and result is None:
        return ""
    line1 = f"마지막 갱신 시각: {_html_escape(ts)}" if ts else ""
    line2 = f"결과: {_html_escape(result)}" if result else ""
    hint = _failed_guard_hint(failed) if failed else ""
    line3 = f"실패: {_html_escape(hint)}" if (result == "FAIL" and hint) else ""
    color = "#3ddc97" if result == "OK" else "#ff6b6b"
    return f'<div class="card" style="margin-bottom:12px; border-left:4px solid {color};"><div class="hint">{line1}</div><div class="hint">{line2}</div>' + (f'<div class="hint" style="color:#ff6b6b;">{line3}</div>' if line3 else '') + '</div>'


def _modules_summary():
    total = len(MODULES)
    ready = sum(1 for m in MODULES if get_effective_module_status(m["key"]) == "READY")
    partial = sum(1 for m in MODULES if get_effective_module_status(m["key"]) == "PARTIAL")
    locked = sum(1 for m in MODULES if get_effective_module_status(m["key"]) == "LOCKED")
    progress = int(round((ready + partial * 0.5) / max(1, total) * 100))
    keys = {"doc_search", "write_approve_export", "helpdesk_ticket"}
    mvp_ready = sum(1 for m in MODULES if m.get("key") in keys and get_effective_module_status(m["key"]) == "READY")
    mvp_partial = sum(1 for m in MODULES if m.get("key") in keys and get_effective_module_status(m["key"]) == "PARTIAL")
    mvp_progress = int(round((mvp_ready + mvp_partial * 0.5) / 3 * 100))
    hard_keys = {"pack_bypass", "raw0_enforce", "mvp_package"}
    hard = {m["key"]: get_effective_module_status(m["key"]) for m in MODULES if m.get("key") in hard_keys}
    return {
        "total": total,
        "ready": ready,
        "partial": partial,
        "locked": locked,
        "progress": progress,
        "mvp_progress": mvp_progress,
        "hard": hard,
    }


# --- Platform UI base template (local-only) ---
BASE_HTML = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{ page_title }}</title>
  <style>
    body{margin:0;font-family:system-ui,-apple-system,"Noto Sans KR",sans-serif;background:#0b1220;color:#e8eefc}
    a{color:inherit;text-decoration:none}
    .layout{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
    .side{border-right:1px solid rgba(255,255,255,.08);padding:18px;background:rgba(255,255,255,.02)}
    .brand{font-weight:900}
    .nav a{display:block;padding:10px 12px;border-radius:10px;margin:6px 0;color:#a9b6d6;border:1px solid transparent}
    .nav a.active{background:rgba(106,168,255,.10);border-color:rgba(106,168,255,.25);color:#e8eefc}
    .nav a:hover{border-color:rgba(255,255,255,.10);color:#e8eefc}
    .main{padding:22px}
    .top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:16px}
    .title{font-size:20px;font-weight:900}
    .subtitle{color:#a9b6d6;font-size:13px;margin-top:6px}
    .pill{display:inline-flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid rgba(255,255,255,.08);border-radius:999px;background:rgba(255,255,255,.03);color:#a9b6d6;font-size:12px}
    .card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:14px}
    .hint{color:#a9b6d6;font-size:12px;line-height:1.45;margin-top:8px}
    pre{white-space:pre-wrap}
    @media (max-width:980px){.layout{grid-template-columns:1fr}}
  </style>
</head>
<body>
<div class="layout">
  <aside class="side">
    <div class="brand">On-Device Platform<br/><span style="color:#a9b6d6;font-weight:700">Local Console</span></div>
    <nav class="nav" style="margin-top:14px;">
      <a href="/" class="{{ 'active' if active == 'dashboard' else '' }}">Dashboard</a>
      <a href="/butler" class="{{ 'active' if active == 'butler' else '' }}">Butler</a>
      <a href="/timeline" class="{{ 'active' if active == 'timeline' else '' }}">Timeline</a>
      <a href="/modules" class="{{ 'active' if active == 'modules' else '' }}">Modules</a>
      <a href="/model-test" class="{{ 'active' if active == 'model-test' else '' }}">Model Test</a>
      <a href="/roadmap" class="{{ 'active' if active == 'roadmap' else '' }}">Roadmap</a>
      <a href="/updates" class="{{ 'active' if active == 'updates' else '' }}">Updates</a>
      <a href="/decisions" class="{{ 'active' if active == 'decisions' else '' }}">Decisions</a>
    </nav>
    <div class="hint" style="margin-top:14px;">
      SSOT 변경은 CHANGELOG/ADR 없이 통과할 수 없습니다.
    </div>
  </aside>
  <main class="main">
    <div class="top">
      <div>
        <div class="title">{{ page_title }}</div>
        <div class="subtitle">{{ page_subtitle }}{% if _recent_ssot_change %} <span class="pill" style="border-color:rgba(255,107,107,.35); color:#ff6b6b;">최근 SSOT 변경 있음</span>{% endif %}</div>
      </div>
      <div>
        <span class="pill">Local</span>
      </div>
    </div>
    {{ content | safe }}
  </main>
</div>
</body>
</html>
"""

def render(active, title, subtitle, content, **ctx):
    return render_template_string(
        BASE_HTML,
        active=active,
        page_title=title,
        page_subtitle=subtitle,
        content=content,
        _recent_ssot_change=_ssot_recent_change_flag(),
        **ctx
    )
# --- end base template ---

EVAL_RESULTS_DIR = os.environ.get("EVAL_RESULTS_DIR", "eval_results").strip()

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def load_eval_results():
    """eval_results/*.json을 읽어 최근순으로 정렬해 반환합니다."""
    files = sorted(glob(str(Path(EVAL_RESULTS_DIR) / "*.json")))
    items = []
    for fp in files:
        try:
            data = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        run = data.get("run") or {}
        metrics = data.get("metrics") or []
        ts = run.get("timestamp_utc") or ""
        ts_key = ts if ts else Path(fp).name
        stage = (run.get("stage") or "NO_STAGE").strip().replace("stage:", "").replace("stage/", "")
        pr_number = run.get("pr_number")
        norm_metrics = []
        for mm in metrics:
            name = mm.get("name")
            val = _safe_float(mm.get("value"))
            hib = mm.get("higher_is_better")
            unit = (mm.get("unit") or "").strip()
            if name and val is not None:
                norm_metrics.append({"name": name, "value": val, "unit": unit, "higher_is_better": bool(hib) if hib is not None else None})
        items.append({
            "file": Path(fp).name,
            "ts_key": str(ts_key),
            "timestamp_utc": ts,
            "stage": stage,
            "pr_number": pr_number,
            "metrics": norm_metrics,
        })
    items.sort(key=lambda x: x["ts_key"], reverse=True)
    return items

def summarize_eval_by_stage(evals):
    """stage별로 최근 2개를 잡아서 metric diff를 계산합니다."""
    by_stage = {}
    for e in evals:
        st = e.get("stage") or "NO_STAGE"
        by_stage.setdefault(st, []).append(e)
    rows = []
    for st, arr in by_stage.items():
        arr = sorted(arr, key=lambda x: x["ts_key"], reverse=True)
        latest = arr[0]
        prev = arr[1] if len(arr) > 1 else None
        latest_m = {m["name"]: m for m in (latest.get("metrics") or [])}
        prev_m = {m["name"]: m for m in ((prev.get("metrics") or []) if prev else [])}
        delta = []
        for name, m in latest_m.items():
            v0 = m["value"]
            v1 = prev_m.get(name, {}).get("value") if prev else None
            d = (v0 - v1) if (v1 is not None) else None
            delta.append({
                "name": name,
                "value": v0,
                "diff": d,
                "unit": m.get("unit", ""),
                "higher_is_better": m.get("higher_is_better"),
            })
        rows.append({"stage": st, "latest": latest, "prev": prev, "delta": delta})
    def stage_key(row):
        st = row["stage"]
        mm = re.match(r"^P(\d+)$", st)
        return (0, -int(mm.group(1))) if mm else (1, st)
    rows.sort(key=stage_key)
    return rows

REPO = os.environ.get("GITHUB_REPO", "").strip()
APP_ID = os.environ.get("GITHUB_APP_ID", "").strip()
INSTALLATION_ID = os.environ.get("GITHUB_INSTALLATION_ID", "").strip()
PRIVATE_KEY_PATH = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()

if REPO and "/" in REPO:
    OWNER, REPO_NAME = REPO.split("/", 1)
else:
    OWNER, REPO_NAME = "", ""

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/vnd.github+json"})

TITLE_STAGE_RE = re.compile(r"\bP(\d+)\b", re.IGNORECASE)  # e.g. P21

def detect_stage(pr_title: str) -> str:
    m = TITLE_STAGE_RE.search(pr_title or "")
    return f"P{m.group(1)}" if m else "NO_STAGE"

def week_bucket(iso_dt: str) -> str:
    dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def compute_weekly_report(prs_grouped: dict):
    """
    이번 주(ISO 주차) 기준으로:
    - 이번 주에 머지된 PR 개수
    - 기능 딱지 분포
    - 딱지/파일분석 커버리지 기반의 '전체 완성도(운영지표)' 산출
    """
    now = datetime.utcnow()
    y, w, _ = now.isocalendar()
    this_week = f"{y}-W{w:02d}"

    merged_count = 0
    feature_counts = {}
    tag_known = 0
    file_fetch_ok = 0

    for _, items in prs_grouped.items():
        for pr in items:
            merged_at = pr.get("merged_at")
            if not merged_at:
                continue
            wk = week_bucket(merged_at)
            if wk != this_week:
                continue

            merged_count += 1
            feats = pr.get("features") or []
            if feats and feats != ["(클릭하면 계산)"]:
                tag_known += 1
                file_fetch_ok += 1
                for f in feats:
                    feature_counts[f] = feature_counts.get(f, 0) + 1

    if merged_count == 0:
        return {
            "week": this_week,
            "merged_count": 0,
            "tag_coverage_percent": 0,
            "file_fetch_ok_percent": 0,
            "overall_percent": 0,
            "by_feature": [{"name": "이번 주 머지 PR 없음", "count": 0, "percent": 0}],
        }

    tag_cov = int(round((tag_known / merged_count) * 100))
    file_ok = int(round((file_fetch_ok / merged_count) * 100))
    overall = int(round((tag_cov * 0.5) + (file_ok * 0.5)))

    rows = []
    total_tagged = sum(feature_counts.values()) or 1
    for name, cnt in sorted(feature_counts.items(), key=lambda kv: kv[1], reverse=True):
        rows.append({"name": name, "count": cnt, "percent": int(round((cnt / total_tagged) * 100))})

    if not rows:
        rows = [{"name": "딱지 미확정(클릭으로 계산 필요)", "count": merged_count, "percent": 100}]

    return {
        "week": this_week,
        "merged_count": merged_count,
        "tag_coverage_percent": tag_cov,
        "file_fetch_ok_percent": file_ok,
        "overall_percent": overall,
        "by_feature": rows,
    }


def load_private_key() -> str:
    if not PRIVATE_KEY_PATH or not os.path.exists(PRIVATE_KEY_PATH):
        raise RuntimeError(
            "GITHUB_APP_PRIVATE_KEY_PATH가 설정되지 않았거나 .pem 파일이 없습니다. "
            "Dashboard/Modules/Updates/Decisions는 그대로 사용할 수 있고, Timeline/API만 GitHub 설정이 필요합니다."
        )
    with open(PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _require_github_config():
    if not REPO:
        raise RuntimeError("GITHUB_REPO를 설정하세요 (예: tristan00037-tristan050/tristan050-ai_ondevice_APP). Timeline/API 사용 시 필요합니다.")
    if not APP_ID:
        raise RuntimeError("GITHUB_APP_ID를 설정하세요 (GitHub App 설정 페이지).")
    if not INSTALLATION_ID:
        raise RuntimeError("GITHUB_INSTALLATION_ID를 설정하세요 (예: 92382330).")


def make_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 30, "exp": now + 9 * 60, "iss": int(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")

def get_installation_token() -> str:
    _require_github_config()
    key = load_private_key()
    app_jwt = make_jwt(APP_ID, key)
    headers = {"Authorization": f"Bearer {app_jwt}"}
    url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
    r = SESSION.post(url, headers=headers, json={})
    if r.status_code >= 300:
        raise RuntimeError(f"Failed to create installation token: {r.status_code} {r.text}")
    return r.json()["token"]

def gh_get(url: str, token: str, params=None):
    headers = {"Authorization": f"token {token}"}
    r = SESSION.get(url, headers=headers, params=params or {})
    if r.status_code >= 300:
        raise RuntimeError(f"GitHub GET failed: {r.status_code} {r.text}")
    return r

def fetch_merged_prs(token: str, per_page=100, max_pages=50):
    url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/pulls"
    prs = []
    for page in range(1, max_pages + 1):
        r = gh_get(url, token, params={
            "state": "closed",
            "per_page": per_page,
            "page": page,
            "sort": "updated",
            "direction": "desc"
        })
        batch = r.json()
        if not batch:
            break
        for pr in batch:
            if pr.get("merged_at"):
                prs.append(pr)
    return prs

# 기능맵(딱지) 규칙: "경로에 어떤 폴더가 포함되는가"로 결정
FEATURE_RULES = [
    ("SSOT", ["docs/ops/contracts/"]),
    ("검증(가드)", ["scripts/verify/"]),
    ("워크플로", [".github/workflows/"]),
    ("MCP", ["tools/mcp_gateway/"]),
    ("운영 스크립트", ["scripts/ops/"]),
]

def features_from_paths(paths: list) -> list:
    hits = []
    for name, needles in FEATURE_RULES:
        for n in needles:
            if any(p.startswith(n) or (n in p) for p in paths):
                hits.append(name)
                break
    return hits or ["기타"]

# 캐시(속도): PR 파일 목록은 자주 바뀌지 않으니 잠깐 캐시
_FILES_CACHE = {}
CACHE_TTL_SEC = int(os.environ.get("FILES_CACHE_TTL_SEC", "300"))  # 기본 5분

def fetch_pr_files(token: str, pr_number: int, max_files: int = 400) -> list:
    now = time.time()
    cached = _FILES_CACHE.get(pr_number)
    if cached and (now - cached[0] < CACHE_TTL_SEC):
        return cached[1]

    files = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/pulls/{pr_number}/files"
        r = gh_get(url, token, params={"per_page": 100, "page": page})
        batch = r.json()
        if not batch:
            break
        for f in batch:
            files.append(f.get("filename", ""))
            if len(files) >= max_files:
                _FILES_CACHE[pr_number] = (now, files, features_from_paths(files))
                return files
        page += 1

    _FILES_CACHE[pr_number] = (now, files, features_from_paths(files))
    return files

def fetch_pr_features_cached(token: str, pr_number: int) -> list:
    now = time.time()
    cached = _FILES_CACHE.get(pr_number)
    if cached and (now - cached[0] < CACHE_TTL_SEC):
        return cached[2]
    paths = fetch_pr_files(token, pr_number)
    return features_from_paths(paths)

def group_prs(prs, token: str, feature_preview_top_n: int):
    grouped = {}
    for idx, pr in enumerate(prs):
        title = pr.get("title", "")
        merged_at = pr.get("merged_at")
        stage = detect_stage(title)
        week = week_bucket(merged_at)
        group_key = stage if stage != "NO_STAGE" else week

        pr_number = pr["number"]
        # 미리보기는 상위 N개 PR에 대해서만 기능딱지를 계산 (속도)
        if idx < feature_preview_top_n:
            feats = fetch_pr_features_cached(token, pr_number)
        else:
            feats = ["(클릭하면 계산)"]

        grouped.setdefault(group_key, []).append({
            "number": pr_number,
            "title": title,
            "merged_at": merged_at,
            "url": pr["html_url"],
            "user": (pr.get("user") or {}).get("login"),
            "features": feats,
        })

    for k in grouped:
        grouped[k].sort(key=lambda x: x["merged_at"], reverse=True)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0], reverse=True))

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>On-Device PR Timeline</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 24px; }
    .top { display:flex; gap:12px; align-items:center; flex-wrap: wrap; }
    .muted { color:#666; font-size: 13px; }
    .card { border:1px solid #ddd; border-radius:10px; padding:14px; margin:14px 0; }
    .k { font-weight:700; }
    a { text-decoration:none; }
    .pr { margin: 10px 0; padding: 10px; border-top: 1px dashed #eee; }
    .badge { display:inline-block; padding:2px 8px; border:1px solid #ccc; border-radius:999px; font-size:12px; margin-right:6px; }
    .btn { border:1px solid #bbb; border-radius:8px; padding:6px 10px; background:#fff; cursor:pointer; }
    pre { background:#fafafa; border:1px solid #eee; padding:10px; border-radius:10px; overflow:auto; }
  </style>
</head>
<body>
  <div class="top">
    <h2 style="margin:0;">PR 타임라인 (라벨 없이 자동 묶기)</h2>
    <div class="muted">규칙: 제목에 P숫자 있으면 그 단계로 묶고, 없으면 주간으로 묶습니다.</div>
  </div>

  <div class="muted" style="margin-top:8px;">
    Repo: {{repo}} / Installation: {{inst}} / Loaded merged PRs: {{count}}
  </div>

  <div class="card" style="border-color:#cfd8dc;">
    <div class="k">이번 주 진행 리포트</div>
    <div class="muted" style="margin-top:6px;">
      기준: 최근 {{count}}개(머지된 PR) 중, 이번 주(ISO 주차) 머지된 PR 기준으로 계산합니다.
    </div>
    <div style="margin-top:10px;">
      <div><span class="k">전체 완성도</span>: {{weekly.overall_percent}}%</div>
      <div class="muted">이번 주 머지 PR: {{weekly.merged_count}}개 / 딱지 커버리지: {{weekly.tag_coverage_percent}}% / 파일분석 성공률: {{weekly.file_fetch_ok_percent}}%</div>
    </div>
    <div style="margin-top:12px;">
      <div class="k" style="margin-bottom:6px;">항목별(딱지) 진행</div>
      <table style="border-collapse:collapse; width:100%; font-size:13px;">
        <thead>
          <tr>
            <th style="text-align:left; border-bottom:1px solid #eee; padding:6px;">항목</th>
            <th style="text-align:right; border-bottom:1px solid #eee; padding:6px;">PR 수</th>
            <th style="text-align:right; border-bottom:1px solid #eee; padding:6px;">비중</th>
          </tr>
        </thead>
        <tbody>
          {% for row in weekly.by_feature %}
          <tr>
            <td style="padding:6px; border-bottom:1px solid #f3f3f3;">{{row.name}}</td>
            <td style="padding:6px; border-bottom:1px solid #f3f3f3; text-align:right;">{{row.count}}</td>
            <td style="padding:6px; border-bottom:1px solid #f3f3f3; text-align:right;">{{row.percent}}%</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <div class="muted" style="margin-top:8px;">
        주의: 이 %는 "제품 완성도"가 아니라 "이번 주에 어느 영역에서 변화가 있었는지"를 보여주는 진행 지표입니다.
      </div>
    </div>
  </div>

  <div class="card" style="border-color:#e0e0e0;">
    <div class="k">AI 성능 리포트</div>
    <div class="muted" style="margin-top:6px;">
      eval_results/*.json을 읽어 Stage별 최신 2개를 비교합니다.
    </div>
    <div style="margin-top:10px;">
      <button class="btn" onclick="loadEvals()">AI 성능 불러오기</button>
      <div id="evals" style="margin-top:10px;"></div>
    </div>
  </div>

  {% for group, items in grouped.items() %}
    <div class="card">
      <div class="k">{{group}}</div>
      <div class="muted">PR {{items|length}}개</div>

      {% for pr in items[:50] %}
        <div class="pr">
          <div>
            <a href="{{pr.url}}" target="_blank">#{{pr.number}}</a>
            {{pr.title}}
            <span class="muted">({{pr.merged_at}} / {{pr.user}})</span>
          </div>

          <div style="margin-top:6px;">
            {% for b in pr.features %}
              <span class="badge">{{b}}</span>
            {% endfor %}
          </div>

          <div style="margin-top:8px;">
            <button class="btn" onclick="loadFiles({{pr.number}})">변경 파일 보기</button>
            <div id="files-{{pr.number}}" class="muted" style="margin-top:8px;"></div>
          </div>
        </div>
      {% endfor %}

      {% if items|length > 50 %}
        <div class="muted">… {{items|length-50}}개 더 있음</div>
      {% endif %}
    </div>
  {% endfor %}

<script>
async function loadEvals() {
  const el = document.getElementById("evals");
  el.textContent = "불러오는 중...";
  try {
    const r = await fetch("/api/evals");
    const j = await r.json();
    if (!r.ok) {
      el.textContent = `오류: ${j.error || r.status}`;
      return;
    }
    const rows = j.rows || [];
    if (rows.length === 0) {
      el.innerHTML = `<div class="muted">eval_results 폴더에 json 파일이 없습니다.</div>`;
      return;
    }
    let html = "";
    for (const row of rows) {
      const st = row.stage;
      const latest = row.latest || {};
      const prev = row.prev || null;
      const delta = row.delta || [];
      html += `<div class="card" style="margin:10px 0;">`;
      html += `<div class="k">Stage: ${st}</div>`;
      html += `<div class="muted">latest: ${latest.file || ""} ${latest.timestamp_utc || latest.ts_key || ""}</div>`;
      if (prev) html += `<div class="muted">prev: ${prev.file || ""} ${prev.timestamp_utc || prev.ts_key || ""}</div>`;
      html += `<table style="border-collapse:collapse; width:100%; font-size:13px; margin-top:8px;">`;
      html += `<thead><tr>
        <th style="text-align:left; border-bottom:1px solid #eee; padding:6px;">지표</th>
        <th style="text-align:right; border-bottom:1px solid #eee; padding:6px;">현재</th>
        <th style="text-align:right; border-bottom:1px solid #eee; padding:6px;">변화</th>
      </tr></thead><tbody>`;
      for (const m of delta) {
        const name = m.name;
        const unit = m.unit || "";
        const v = (m.value === null || m.value === undefined) ? "" : m.value.toString();
        const d = (m.diff === null || m.diff === undefined) ? "" : (m.diff >= 0 ? "+" + m.diff.toString() : m.diff.toString());
        html += `<tr>
          <td style="padding:6px; border-bottom:1px solid #f3f3f3;">${name}</td>
          <td style="padding:6px; border-bottom:1px solid #f3f3f3; text-align:right;">${v} ${unit}</td>
          <td style="padding:6px; border-bottom:1px solid #f3f3f3; text-align:right;">${d} ${unit}</td>
        </tr>`;
      }
      html += `</tbody></table>`;
      if (latest.pr_number) {
        html += `<div class="muted" style="margin-top:8px;">연결 PR: #${latest.pr_number}</div>`;
      }
      html += `</div>`;
    }
    el.innerHTML = html;
  } catch (e) {
    el.textContent = "오류: " + e;
  }
}
async function loadFiles(prNumber) {
  const el = document.getElementById(`files-${prNumber}`);
  el.textContent = "불러오는 중...";
  try {
    const r = await fetch(`/api/pr/${prNumber}/files`);
    const j = await r.json();
    if (!r.ok) {
      el.textContent = `오류: ${j.error || r.status}`;
      return;
    }
    const lines = (j.files || []).slice(0, 200).map(f => `- ${f}`).join("\\n");
    const feats = (j.features || []).join(", ");
    el.innerHTML = `
      <div class="muted">기능 딱지: ${feats}</div>
      <pre>${lines}${(j.files || []).length > 200 ? "\\n... (200개까지만 표시)" : ""}</pre>
    `;
  } catch (e) {
    el.textContent = "오류: " + e;
  }
}
</script>
</body>
</html>
"""

app = Flask(__name__)

@app.get("/")
def dashboard_page():
    ms = _modules_summary()

    def _status_color(st):
        if st == "READY":
            return "#3ddc97"
        if st == "PARTIAL":
            return "#ffd166"
        if st == "LOCKED":
            return "#ff6b6b"
        return "#a9b6d6"

    hard = ms["hard"]
    refresh_banner = _refresh_banner_html()
    html = refresh_banner + f"""
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
  <h3>Dashboard</h3>
      <div class="hint">이 화면은 '목표 대비 진행'을 한눈에 보기 위한 내부 콘솔입니다.</div>
      <div style="margin-top:10px;">
        <a href="/api/refresh?redirect=/" class="pill" style="text-decoration:none;">🔄 상태 갱신(verify 실행)</a>
        <span class="hint" style="margin-left:8px;">갱신 후 자동 새로고침됩니다. (약 1~2분 소요)</span>
      </div>
    </div>

    <div class="card" style="margin-top:12px;">
      <h3>전체 모듈 진행률</h3>
      <div class="hint">READY는 100점, PARTIAL은 50점으로 계산합니다.</div>
      <div style="font-size:28px; font-weight:900; margin-top:10px;">{ms["progress"]}%</div>
      <div class="hint">READY {ms["ready"]} / PARTIAL {ms["partial"]} / LOCKED {ms["locked"]} (총 {ms["total"]})</div>
      <div style="margin-top:10px;"><a href="/modules" class="pill">Modules 보기</a></div>
    </div>

    <div class="card" style="margin-top:12px;">
      <h3>MVP(전사 공통 3 시나리오) 진행률</h3>
      <div class="hint">문서검색/요약 · 초안+승인+반출 · 헬프데스크 티켓</div>
      <div style="font-size:28px; font-weight:900; margin-top:10px;">{ms["mvp_progress"]}%</div>
      <div class="hint">3 시나리오가 READY/PARTIAL로 바뀌면 '상품이 보이는 상태'로 진입합니다.</div>
    </div>

    <div class="card" style="margin-top:12px;">
      <h3>추가 고정 3개 상태</h3>
      <div class="hint">업무팩 우회 봉인 / 원문0 전수 봉인 / 상품성 패키지</div>
      <div style="margin-top:10px;">
        <span class="pill" style="color:{_status_color(hard.get("pack_bypass", "LOCKED"))}">업무팩 우회 봉인: {hard.get("pack_bypass", "LOCKED")}</span>
        <span class="pill" style="color:{_status_color(hard.get("raw0_enforce", "LOCKED"))}">원문0 전수 봉인: {hard.get("raw0_enforce", "LOCKED")}</span>
        <span class="pill" style="color:{_status_color(hard.get("mvp_package", "LOCKED"))}">상품성 패키지: {hard.get("mvp_package", "LOCKED")}</span>
      </div>
    </div>
    """
    html = html + _model_test_summary_html()
    return render("dashboard", "Dashboard", "목표 대비 진행/리스크/변경 이력을 한눈에 확인합니다.", html)


@app.get("/timeline")
def index():
    max_pages = int(os.environ.get("MAX_PAGES", "50"))
    feature_preview_top_n = int(os.environ.get("FEATURE_PREVIEW_TOP_N", "80"))
    token = get_installation_token()
    prs = fetch_merged_prs(token, max_pages=max_pages)
    grouped = group_prs(prs, token, feature_preview_top_n)
    weekly_report = compute_weekly_report(grouped)
    return render_template_string(
        HTML,
        repo=REPO,
        inst=INSTALLATION_ID,
        count=len(prs),
        grouped=grouped,
        weekly=weekly_report,
    )

@app.get("/api/groups")
def api_groups():
    max_pages = int(os.environ.get("MAX_PAGES", "50"))
    feature_preview_top_n = int(os.environ.get("FEATURE_PREVIEW_TOP_N", "80"))
    token = get_installation_token()
    prs = fetch_merged_prs(token, max_pages=max_pages)
    grouped = group_prs(prs, token, feature_preview_top_n)
    weekly_report = compute_weekly_report(grouped)
    return jsonify({"repo": REPO, "installation_id": INSTALLATION_ID, "count": len(prs), "groups": grouped, "weekly": weekly_report})

@app.get("/api/evals")
def api_evals():
    try:
        evals = load_eval_results()
        rows = summarize_eval_by_stage(evals)
        return jsonify({"rows": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/pr/<int:pr_number>/files")
def api_pr_files(pr_number: int):
    try:
        token = get_installation_token()
        files = fetch_pr_files(token, pr_number)
        feats = features_from_paths(files)
        return jsonify({"pr_number": pr_number, "files": files, "features": feats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# SSOT Updates / Decisions (CHANGELOG + ADR)
SSOT_ROOT = Path(__file__).resolve().parent.parent / "docs" / "ssot"


def _ssot_recent_change_flag():
    """
    CHANGELOG 최신 섹션 날짜가 오늘(또는 최근 7일)이면 True.
    """
    try:
        txt = _read_text_safe(SSOT_ROOT / "CHANGELOG.md")
        m = re.search(r"^##\s+(\d{4}-\d{2}-\d{2})", txt, re.MULTILINE)
        if not m:
            return False
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        return (date.today() - d).days <= 7
    except Exception:
        return False


def _extract_latest_changelog_entry(changelog_text: str):
    """
    CHANGELOG에서 가장 최근 섹션(## YYYY-MM-DD) 1개를 추출하고,
    그 안의 '무엇/왜/영향/검증' 4줄을 찾아 반환합니다.
    """
    lines = changelog_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = lines[start:end]
    wanted = {"- 무엇:": None, "- 왜:": None, "- 영향:": None, "- 검증:": None}
    for ln in section:
        for k in list(wanted.keys()):
            if ln.strip().startswith(k):
                wanted[k] = ln.strip()[len(k):].strip()
    if all(v is None for v in wanted.values()):
        return {"title": section[0].replace("## ", "").strip(), "items": []}
    items = []
    for k in ["- 무엇:", "- 왜:", "- 영향:", "- 검증:"]:
        v = wanted.get(k)
        if v is not None:
            items.append((k.replace("- ", "").replace(":", ""), v))
    return {"title": section[0].replace("## ", "").strip(), "items": items}


def _read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"[ERROR] cannot read {path}: {e}"


def _parse_adr_header(text: str):
    """
    ADR에서 제목(첫 줄 # ...)과 - 날짜:, - 상태: 를 가볍게 파싱합니다(없으면 빈 값).
    """
    title = ""
    date = ""
    status = ""
    for ln in text.splitlines()[:40]:
        if ln.startswith("# "):
            title = ln[2:].strip()
        if ln.lower().startswith("- 날짜:") or ln.startswith("- 날짜:"):
            date = ln.split(":", 1)[1].strip()
        if ln.lower().startswith("- 상태:") or ln.startswith("- 상태:"):
            status = ln.split(":", 1)[1].strip()
    return {"title": title, "date": date, "status": status}


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))

@app.get("/updates")
def updates_page():
    changelog = _read_text_safe(SSOT_ROOT / "CHANGELOG.md")
    latest = _extract_latest_changelog_entry(changelog)
    latest_html = ""
    if latest:
        rows = ""
        for k, v in latest.get("items", []):
            rows += f"<tr><td style='width:90px; color:#a9b6d6; font-weight:800;'>{k}</td><td>{_html_escape(v)}</td></tr>"
        if not rows:
            rows = "<tr><td>요약 항목이 없습니다.</td></tr>"
        latest_html = f"""<div class="card" style="margin-bottom:12px;">
          <h3>가장 최근 변경(요약)</h3>
          <div class="hint">CHANGELOG의 가장 위 섹션(최신)을 자동 요약합니다.</div>
          <div class="hint" style="margin-top:8px;">날짜: {_html_escape(latest.get('title', ''))}</div>
          <table class="table" style="margin-top:10px; width:100%; border-collapse:collapse;">
            <tbody>{rows}</tbody>
          </table>
        </div>"""
    escaped = _html_escape(changelog)
    html = latest_html + f'<div class="card"><h3>SSOT ChangeLog</h3><div class="hint">SSOT가 바뀌면 반드시 여기에 기록됩니다.</div><pre style="white-space:pre-wrap; margin-top:10px;">{escaped}</pre></div>'
    return render("updates", "Updates", "SSOT 변경 기록(CHANGELOG)과 결정 기록(ADR)을 플랫폼 화면에서 확인합니다.", html)

@app.get("/decisions")
def decisions_page():
    adr_dir = SSOT_ROOT / "DECISIONS"
    files = sorted(adr_dir.glob("ADR-*.md"), key=lambda p: p.name, reverse=True)[:5]
    items = ""
    for f in files:
        name = f.name
        body = _read_text_safe(f)
        meta = _parse_adr_header(body)
        title = meta.get("title") or name
        date = meta.get("date") or ""
        status = meta.get("status") or ""
        items += f'<li style="margin:8px 0;"><a href="/decisions/{name}"><b>{_html_escape(title)}</b></a><div class="hint">{_html_escape(name)}'
        if date:
            items += f" · {_html_escape(date)}"
        if status:
            items += f" · {_html_escape(status)}"
        items += "</div></li>"
    if not items:
        items = "<li>ADR 파일이 없습니다.</li>"
    html = f'<div class="card"><h3>Decisions (ADR)</h3><div class="hint">방향 변경은 ADR로만 기록됩니다. 최근 ADR을 플랫폼 화면에서 확인합니다.</div><ul style="margin-top:10px;">{items}</ul></div>'
    return render("decisions", "Decisions", "방향 변경은 ADR로만 기록됩니다. 최근 ADR을 플랫폼 화면에서 확인합니다.", html)

@app.get("/decisions/<path:name>")
def decision_view(name: str):
    if ".." in name or "/" in name:
        return "Invalid path", 400
    path = (SSOT_ROOT / "DECISIONS" / name).resolve()
    root = SSOT_ROOT.resolve()
    if not str(path).startswith(str(root)):
        return "Invalid path", 400
    body = _read_text_safe(path)
    escaped = _html_escape(body)
    html = f'<div class="card"><h3>ADR</h3><div class="hint">{_html_escape(name)}</div><pre style="white-space:pre-wrap; margin-top:10px;">{escaped}</pre><p style="margin-top:10px;"><a href="/decisions">← ADR 목록</a> · <a href="/">타임라인</a></p></div>'
    return render("decisions", "Decisions", "ADR 상세 내용을 플랫폼 화면에서 확인합니다.", html)


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

    _verify_cache["running"] = True
    try:
        _run_verify_and_parse()
    finally:
        _verify_cache["running"] = False


@app.get("/diagnostics/verify-cache")
def diagnostics_verify_cache():
    """저장된 verify 결과(.local/verify_cache.json)를 화면에서 확인. 마스킹/길이 제한 유지."""
    try:
        if _VERIFY_CACHE_PATH.exists():
            data = json.loads(_VERIFY_CACHE_PATH.read_text(encoding="utf-8"))
        else:
            data = {}
    except Exception as e:
        data = {"_error": str(e)[:200]}
    if data.get("result") == "FAIL" and data.get("failed_guard"):
        data["failed_guard_hint"] = _failed_guard_hint(data["failed_guard"])
    data["_note"] = "원문·stderr 미저장. 키/값·결과만 저장됨."
    return jsonify(data)


@app.get("/api/refresh_status")
def api_refresh_status():
    """갱신 실행 여부와 결과(마지막 갱신 시각/OK·FAIL/실패 가드) 반환."""
    return jsonify({
        "running": _verify_cache.get("running", False),
        "result_ts": _verify_cache.get("result_ts"),
        "result": _verify_cache.get("result"),
        "failed_guard": _verify_cache.get("failed_guard"),
    })


@app.get("/api/refresh")
def api_refresh():
    """백그라운드로 verify 실행 후, '갱신 중' 페이지를 보여주고 완료 시 redirect."""
    redirect_to = request.args.get("redirect", "").strip() or "/"
    if not redirect_to.startswith("/"):
        redirect_to = "/"
    if _verify_cache.get("running"):
        html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>갱신 중</title></head><body style="font-family:sans-serif;padding:2em;">
        <p>⏳ 상태 갱신 실행 중… (이미 다른 갱신이 진행 중입니다)</p>
        <p><a href="/">Dashboard로</a></p>
        <script>setTimeout(function(){ location.href = "/api/refresh_status"; }, 2000);</script>
        </body></html>"""
        return html
    threading.Thread(target=_run_verify_background, daemon=True).start()
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>갱신 중</title></head><body style="font-family:sans-serif;padding:2em;background:#0b1220;color:#e8eefc;">
    <p>⏳ 상태 갱신 실행 중… (1~2분 소요)</p>
    <p class="hint" style="color:#a9b6d6;">완료되면 자동으로 이동합니다.</p>
    <p><a href="{esc(redirect_to)}" style="color:#6aa8ff;">취소하고 이동</a></p>
    <script>
    (function poll() {{
      fetch("/api/refresh_status")
        .then(r => r.json())
        .then(function(d) {{
          if (!d.running) {{ location.href = "{esc(redirect_to)}"; return; }}
          setTimeout(poll, 2000);
        }})
        .catch(function() {{ setTimeout(poll, 2000); }});
    }})();
    </script>
    </body></html>"""
    return html


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

# Roadmap: Phase 1 체크리스트 (SSOT v1.0 기준)
ROADMAP_PHASE1 = [
    {"key": "doc_search", "label": "문서 검색/요약 (시나리오 #1)", "order": 1},
    {"key": "write_approve_export", "label": "초안 + 승인 + 반출 (시나리오 #2, Export 2단계)", "order": 2},
    {"key": "helpdesk_ticket", "label": "헬프데스크 티켓 (시나리오 #3)", "order": 3},
    {"key": "raw0_enforce", "label": "raw0 전수 봉인 (로그/예외/리포트)", "order": 4},
    {"key": "pack_bypass", "label": "업무팩 우회 봉인", "order": 5},
    {"key": "mvp_package", "label": "상품성 패키지 (3시나리오 + 운영콘솔 v0)", "order": 6},
]


@app.get("/roadmap")
def roadmap_page():
    items = []
    next_locked_key = None
    for row in sorted(ROADMAP_PHASE1, key=lambda x: x["order"]):
        st = get_effective_module_status(row["key"])
        if next_locked_key is None and st != "READY":
            next_locked_key = row["key"]
        color = "#3ddc97" if st == "READY" else "#ffd166" if st == "PARTIAL" else "#ff6b6b"
        is_next = row["key"] == next_locked_key
        items.append({
            "label": row["label"],
            "status": st,
            "color": color,
            "next": is_next,
        })
    cards = ""
    for x in items:
        next_badge = ' <span class="pill" style="border-color:#ffd166; color:#ffd166;">다음 1개</span>' if x["next"] else ""
        cards += f"""
        <div class="card" style="margin:10px 0; border-left:4px solid {x['color']};">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span>{_html_escape(x['label'])}</span>
            <span class="pill" style="color:{x['color']};">{x['status']}</span>{next_badge}
          </div>
        </div>
        """
    html = f"""
    <div class="card">
      <h3>Roadmap (Phase 1)</h3>
      <div class="hint">SSOT v1.0 기준. 3시나리오 E2E · 승인 반출 0 · raw0 전수 · pack 우회 봉인 · 성능 예산. 상태는 Modules와 연동됩니다.</div>
    </div>
    {cards}
    """
    return render("roadmap", "Roadmap", "남은 개발 목표(Phase 1) 및 다음 1개 강조", html)


# --- Model Test ---
MODEL_TESTS_FILE = _REPO_ROOT / "docs" / "ssot" / "MODEL_TESTS_V1.json"
MODEL_TEST_HISTORY_FILE = _APP_ROOT / ".local" / "model_test_history.json"


def _load_model_tests():
    try:
        return json.loads(MODEL_TESTS_FILE.read_text(encoding="utf-8")).get("tests", [])
    except Exception:
        return []


def _load_model_test_history():
    try:
        return json.loads(MODEL_TEST_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_model_test_history(items):
    MODEL_TEST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_TEST_HISTORY_FILE.write_text(json.dumps(items[-30:], ensure_ascii=False, indent=2), encoding="utf-8")


def _run_model_test(test_id: str):
    tests = _load_model_tests()
    t = next((x for x in tests if x.get("id") == test_id), None)
    if not t:
        return {"ok": False, "error": "UNKNOWN_TEST", "message": f"알 수 없는 테스트: {test_id}"}
    timeout_sec = int(t.get("timeout_sec", 30))
    cmd = t.get("command", "")
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(_REPO_ROOT),
        )
        out = (proc.stdout or "").strip()
        if not out:
            result = {"ok": False, "error": "EMPTY_OUTPUT", "message": "테스트 출력이 없습니다."}
        else:
            try:
                result = json.loads(out)
            except Exception:
                result = {"ok": False, "error": "NON_JSON_OUTPUT", "message": out[:300]}
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": "TIMEOUT", "message": f"{timeout_sec}초 내에 끝나지 않았습니다."}
    except Exception as e:
        result = {"ok": False, "error": "EXCEPTION", "message": str(e)[:300]}
    result["test_id"] = test_id
    result["test_name"] = t.get("name", test_id)
    return result


def _model_test_summary_html():
    tests = _load_model_tests()
    history = list(reversed(_load_model_test_history()))
    buttons = ""
    for t in tests:
        buttons += f'<a class="pill" href="/api/model-test/run/{_html_escape(t.get("id", ""))}">{_html_escape(t.get("name", ""))}</a> '
    latest_html = ""
    if history:
        h = history[0]
        latest_html = f"""
        <div class="hint" style="margin-top:8px;"><b>마지막 테스트</b>: {_html_escape(str(h.get("ts", "")))}</div>
        <div class="hint"><b>이름</b>: {_html_escape(str(h.get("test_name", "")))}</div>
        <div class="hint"><b>결과</b>: {_html_escape("PASS" if h.get("ok") else "FAIL")}</div>
        <pre style="white-space:pre-wrap; margin-top:10px;">{_html_escape(json.dumps(h, ensure_ascii=False, indent=2)[:700])}</pre>
        """
    else:
        latest_html = '<div class="hint" style="margin-top:8px;">아직 실행 기록이 없습니다.</div>'
    return f"""
    <div class="card" style="margin-top:12px;">
      <h3>Model Test</h3>
      <div class="hint">
        온디바이스 AI 모델을 여기서 바로 테스트합니다.
        최신 결과 보기 / 최신 2개 비교 / 예산 기준 체크를 실행할 수 있습니다.
      </div>
      <div style="margin-top:10px;">{buttons if buttons else '<span class="hint">등록된 테스트가 없습니다.</span>'}</div>
      {latest_html}
      <div style="margin-top:10px;"><a class="pill" href="/model-test">Model Test 전체 보기</a></div>
    </div>
    """


@app.get("/model-test")
def model_test_page():
    tests = _load_model_tests()
    history = list(reversed(_load_model_test_history()))
    buttons = ""
    for t in tests:
        buttons += f"""
        <div class="card" style="margin:10px 0;">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
            <div style="font-weight:900;">{_html_escape(t.get('name', ''))}</div>
            <a class="pill" href="/api/model-test/run/{_html_escape(t.get('id', ''))}">실행</a>
          </div>
          <div class="hint" style="margin-top:8px;">명령: {_html_escape(t.get('command', ''))}</div>
        </div>
        """
    hist_rows = ""
    for h in history[:10]:
        hist_rows += f"""
        <tr>
          <td>{_html_escape(str(h.get('ts', '')))}</td>
          <td>{_html_escape(str(h.get('test_name', '')))}</td>
          <td>{_html_escape('PASS' if h.get('ok') else 'FAIL')}</td>
          <td><pre style="white-space:pre-wrap; margin:0;">{_html_escape(json.dumps(h, ensure_ascii=False, indent=2)[:500])}</pre></td>
        </tr>
        """
    html = f"""
    <div class="card">
      <h3>Model Test</h3>
      <div class="hint">
        여기서 온디바이스 AI 모델 테스트를 직접 실행합니다.
        최신 결과 보기 / 최신 2개 비교 / 예산 기준 체크를 버튼으로 실행할 수 있습니다.
      </div>
    </div>
    <div style="margin-top:12px;">
      {buttons if buttons else '<div class="card"><div class="hint">등록된 테스트가 없습니다.</div></div>'}
    </div>
    <div class="card" style="margin-top:12px;">
      <h3>최근 실행 결과</h3>
      <table class="table">
        <thead><tr><th>시각</th><th>테스트</th><th>결과</th><th>내용</th></tr></thead>
        <tbody>{hist_rows if hist_rows else '<tr><td colspan="4">아직 실행 기록이 없습니다.</td></tr>'}</tbody>
      </table>
    </div>
    """
    return render("model-test", "Model Test", "온디바이스 AI 모델을 계속 테스트하고 결과를 누적해서 봅니다.", html)


@app.get("/api/model-test/run/<test_id>")
def api_model_test_run(test_id: str):
    result = _run_model_test(test_id)
    hist = _load_model_test_history()
    result["ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    hist.append(result)
    _save_model_test_history(hist)
    return redirect("/model-test")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    app.run(host="127.0.0.1", port=port, debug=True)
