from __future__ import annotations
import hashlib, json, zipfile
from pathlib import Path
from typing import Any, Iterable

REQUIRED_FIELDS = ("prompt", "completion", "function", "task_type", "lang", "format", "source", "split")

def deterministic_split(prompt: str) -> str:
    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return "validation" if int(h[:8], 16) % 20 == 0 else "train"

def build_row(prompt: str, completion: str, function: str, source: str, dataset_name: str = "", source_file: str = "", record_id: str = "", quality_flags=None) -> dict:
    return {
        "prompt": prompt.strip(),
        "completion": completion.strip(),
        "function": function,
        "task_type": function,
        "lang": "ko",
        "format": "qwen2.5_chat",
        "source": source,
        "split": deterministic_split(prompt),
        "dataset_name": dataset_name,
        "source_file": source_file,
        "record_id": record_id,
        "quality_flags": quality_flags or [],
    }

def safe_zip_members(z: zipfile.ZipFile) -> list[str]:
    safe = []
    for name in z.namelist():
        if '..' in name or name.startswith('/'):
            continue
        safe.append(name)
    return safe

def record_zip_inventory(zip_fp: Path, z: zipfile.ZipFile, inventory: dict):
    infos = z.infolist()
    inventory[str(zip_fp)] = {
        "member_count": len(infos),
        "total_compressed": sum(i.compress_size for i in infos),
        "total_uncompressed": sum(i.file_size for i in infos),
        "max_single_file": max((i.file_size for i in infos), default=0),
    }

def write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def write_jsonl(path: Path, rows: Iterable[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
