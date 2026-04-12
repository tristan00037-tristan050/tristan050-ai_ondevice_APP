from __future__ import annotations
import csv, hashlib, json, random, re
from pathlib import Path
from typing import Any, Iterable

REQUIRED_FIELDS = ["prompt","completion","function","task_type","lang","format","source","split"]
FUNCTIONS = {"tool_call","rewrite","retrieval_transform","dialogue","policy_sensitive","summarize"}

def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def deterministic_split(prompt: str) -> str:
    return "validation" if int(sha16(prompt), 16) % 20 == 0 else "train"

def is_korean_text(text: str, min_chars: int = 3) -> bool:
    return sum(1 for c in text if "\uac00" <= c <= "\ud7a3") >= min_chars

def ensure_aihub_source(source: str) -> str:
    return source if source.startswith("aihub_") else f"aihub_{source}"

def build_row(prompt: str, completion: str, function: str, source: str, **extra: Any) -> dict[str, Any]:
    row = {
        "prompt": prompt.strip(),
        "completion": completion.strip(),
        "function": function,
        "task_type": function,
        "lang": "ko",
        "format": "qwen2.5_chat",
        "source": ensure_aihub_source(source),
        "split": deterministic_split(prompt),
    }
    row.update(extra)
    return row

def jsonl_write(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count

def jsonl_read(path: str | Path) -> list[dict[str, Any]]:
    out = []
    path = Path(path)
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def sniff_records(path: Path, sample_count: int = 3) -> tuple[str, list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                recs = data["data"]
            else:
                recs = [data]
        else:
            recs = data
        return "json", recs[:sample_count]
    if suffix == ".jsonl":
        return "jsonl", jsonl_read(path)[:sample_count]
    if suffix == ".csv":
        with path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return "csv", rows[:sample_count]
    raise ValueError(f"unsupported file: {path}")

def find_sample_files(dataset_dir: str | Path, limit: int = 3) -> list[Path]:
    dataset_dir = Path(dataset_dir)
    cand = []
    for ext in ("*.json","*.jsonl","*.csv"):
        cand.extend(sorted(dataset_dir.rglob(ext)))
    return cand[:limit]

def summarize_fields(records: list[dict[str, Any]]) -> list[str]:
    fields = set()
    for r in records:
        fields.update(r.keys())
    return sorted(fields)

def detect_text_candidates(fields: list[str]) -> list[str]:
    keys = []
    lowers = [f.lower() for f in fields]
    for f in fields:
        lf = f.lower()
        if any(tok in lf for tok in ["text","utter","question","query","instruction","answer","response","document","content","summary","sql"]):
            keys.append(f)
    if not keys:
        keys = fields[:5]
    return keys

def try_get(d: dict, *cands: str):
    for c in cands:
        if c in d and d[c] not in (None,""):
            return d[c]
    return None

def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, (dict,list)):
        return json.dumps(s, ensure_ascii=False)
    return str(s).strip()

def polite_present(text: str) -> bool:
    return any(k in text for k in ["죄송","안내","드립니다","감사","부탁"])

def preserve_ratio(source: str, target: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    hit = sum(1 for k in keywords if k in target)
    return hit / max(len(keywords),1)

def extract_event_fields(text: str) -> dict[str, str]:
    # simple regex-based event extractor for sample/demo paths
    def pick(patterns):
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return ""
    return {
        "이벤트": pick([r"행사명[: ]*([^\n,]+)", r"이벤트[: ]*([^\n,]+)", r"회의[: ]*([^\n,]+)"]),
        "일시": pick([r"일시[: ]*([^\n,]+)", r"날짜[: ]*([^\n,]+)"]),
        "장소": pick([r"장소[: ]*([^\n,]+)"]),
        "참여자": pick([r"참여자[: ]*([^\n,]+)", r"참석자[: ]*([^\n,]+)"]),
        "주최": pick([r"주최[: ]*([^\n,]+)"]),
    }

def tool_name_from_sql(sql: str) -> str:
    s = sql.strip().upper()
    if s.startswith("SELECT"):
        return "db_query"
    if s.startswith("INSERT"):
        return "db_insert"
    if s.startswith("UPDATE"):
        return "db_update"
    if s.startswith("DELETE"):
        return "db_delete"
    return "db_execute"

def help_target(ap):
    ap.add_argument("--target", type=int, default=None)
