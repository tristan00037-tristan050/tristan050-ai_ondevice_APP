import os, re, time, json
from datetime import datetime
from pathlib import Path
from glob import glob
import requests
import jwt
from flask import Flask, jsonify, render_template_string

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

if not REPO:
    raise SystemExit("GITHUB_REPO is required (e.g. tristan00037-tristan050/tristan050-ai_ondevice_APP)")
if not APP_ID:
    raise SystemExit("GITHUB_APP_ID is required (GitHub App settings page -> App ID)")
if not INSTALLATION_ID:
    raise SystemExit("GITHUB_INSTALLATION_ID is required (e.g. 92382330)")
if not PRIVATE_KEY_PATH or not os.path.exists(PRIVATE_KEY_PATH):
    raise SystemExit("GITHUB_APP_PRIVATE_KEY_PATH must point to your downloaded .pem file")

OWNER, REPO_NAME = REPO.split("/", 1)

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
    with open(PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()

def make_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 30, "exp": now + 9 * 60, "iss": int(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")

def get_installation_token() -> str:
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
def index():
    max_pages = int(os.environ.get("MAX_PAGES", "50"))
    feature_preview_top_n = int(os.environ.get("FEATURE_PREVIEW_TOP_N", "80"))  # 상위 N개 PR만 미리 계산
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

def _read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"[ERROR] cannot read {path}: {e}"

def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))

@app.get("/updates")
def updates_page():
    changelog = _read_text_safe(SSOT_ROOT / "CHANGELOG.md")
    escaped = _html_escape(changelog)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Updates</title></head><body>
    <div style="max-width:800px; margin:1em auto; font-family:sans-serif;">
      <h2>Updates (SSOT ChangeLog)</h2>
      <p style="color:#666;">SSOT가 바뀌면 반드시 여기에 기록됩니다.</p>
      <pre style="white-space:pre-wrap; background:#f5f5f5; padding:1em;">{escaped}</pre>
      <p><a href="/">← 타임라인으로</a></p>
    </div></body></html>"""
    return html

@app.get("/decisions")
def decisions_page():
    adr_dir = SSOT_ROOT / "DECISIONS"
    files = sorted(adr_dir.glob("ADR-*.md"), key=lambda p: p.name, reverse=True)[:5]
    items = "".join(f'<li><a href="/decisions/{f.name}">{f.name}</a></li>' for f in files)
    if not items:
        items = "<li>ADR 파일이 없습니다.</li>"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Decisions</title></head><body>
    <div style="max-width:800px; margin:1em auto; font-family:sans-serif;">
      <h2>Decisions (ADR)</h2>
      <p style="color:#666;">방향 변경은 ADR로만 기록됩니다.</p>
      <ul>{items}</ul>
      <p><a href="/">← 타임라인으로</a></p>
    </div></body></html>"""
    return html

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
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{_html_escape(name)}</title></head><body>
    <div style="max-width:800px; margin:1em auto; font-family:sans-serif;">
      <pre style="white-space:pre-wrap; background:#f5f5f5; padding:1em;">{escaped}</pre>
      <p><a href="/decisions">← ADR 목록</a> <a href="/">타임라인</a></p>
    </div></body></html>"""
    return html

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    app.run(host="127.0.0.1", port=port, debug=True)
