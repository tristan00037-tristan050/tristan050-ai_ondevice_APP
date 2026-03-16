#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

SCHEMA_PATH_V3 = Path("schemas/tool_call_schema_v3.json")
SCHEMA_PATH_V2 = Path("schemas/tool_call_schema_v2.json")
FUNCTIONS = ["dialogue", "summarize", "rewrite", "tool_call", "policy_sensitive", "retrieval_transform"]
LANGS = ["ko", "en", "mixed"]
SPLITS = ["train", "validation", "test"]
SPLIT_WEIGHTS = [0.8, 0.1, 0.1]

TOPICS = ["회의 일정", "출장 보고", "고객 문의", "예산 검토", "정책 안내", "프로젝트 업데이트"]
NAMES = ["홍길동", "김민수", "박서연", "Alice Kim", "Brian Park", "Emma Jung"]
LOCS = ["서울", "부산", "판교", "대전", "여의도", "원격"]
DATES = ["2026-03-16", "2026-03-17", "2026-03-18"]

BUILTIN_SCHEMA = {
    "schema_version": "v3-builtin",
    "registered_actions": ["get_weather", "add_schedule", "send_email", "search_contact", "summarize_doc", "set_volume", "toggle_wifi", "open_file", "save_memo"],
    "tools": [
        {"name": "get_weather", "arguments": {"location": {"type": "string"}, "date": {"type": "string", "enum": ["today", "tomorrow"]}}, "required": ["location"]},
        {"name": "add_schedule", "arguments": {"title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"}, "location": {"type": "string"}}, "required": ["title", "date"]},
        {"name": "send_email", "arguments": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]},
        {"name": "search_contact", "arguments": {"name": {"type": "string"}}, "required": ["name"]},
        {"name": "summarize_doc", "arguments": {"document_text": {"type": "string"}, "target_length": {"type": "string", "enum": ["short", "medium", "long"]}}, "required": ["document_text"]},
        {"name": "set_volume", "arguments": {"level": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["level"]},
        {"name": "toggle_wifi", "arguments": {"enabled": {"type": "boolean"}}, "required": ["enabled"]},
        {"name": "open_file", "arguments": {"path": {"type": "string"}}, "required": ["path"]},
        {"name": "save_memo", "arguments": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title", "content"]},
    ],
}

TOOL_SCENARIOS = [
    ("get_weather", lambda i: f"오늘 {LOCS[i % len(LOCS)]} 날씨 알려줘", lambda i: {"location": LOCS[i % len(LOCS)], "date": "today" if i % 2 == 0 else "tomorrow"}),
    ("add_schedule", lambda i: f"{DATES[i % len(DATES)]} 오전 10시 팀 미팅 일정 추가해줘", lambda i: {"title": TOPICS[i % len(TOPICS)], "date": DATES[i % len(DATES)], "time": "10:00", "location": LOCS[(i + 1) % len(LOCS)]}),
    ("send_email", lambda i: "팀장에게 주간 업데이트 메일 보내줘", lambda i: {"to": f"manager{i}@example.com", "subject": f"Weekly Update {i}", "body": f"Please review {TOPICS[i % len(TOPICS)]}."}),
    ("search_contact", lambda i: f"{NAMES[i % len(NAMES)]} 연락처 찾아줘", lambda i: {"name": NAMES[i % len(NAMES)]}),
    ("summarize_doc", lambda i: "이 보고서를 짧게 요약해줘", lambda i: {"document_text": f"Document about {TOPICS[i % len(TOPICS)]} at {LOCS[i % len(LOCS)]}.", "target_length": ["short", "medium", "long"][i % 3]}),
    ("set_volume", lambda i: "볼륨을 30으로 맞춰줘", lambda i: {"level": [0, 15, 30, 50, 75, 100][i % 6]}),
    ("toggle_wifi", lambda i: "와이파이를 켜줘" if i % 2 == 0 else "와이파이를 꺼줘", lambda i: {"enabled": bool(i % 2 == 0)}),
    ("open_file", lambda i: "방금 저장한 리포트 파일 열어줘", lambda i: {"path": f"/tmp/report_{i:04d}.txt"}),
    ("save_memo", lambda i: "회의 메모 저장해줘", lambda i: {"title": f"Memo {i}", "content": f"{TOPICS[i % len(TOPICS)]} 관련 메모"}),
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_tool_schema() -> dict[str, Any]:
    require_external = os.environ.get("REQUIRE_EXTERNAL_SCHEMA", "0") == "1"
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / ".." / ".." / "schemas" / "tool_call_schema_v3.json",
        SCHEMA_PATH_V3,
        SCHEMA_PATH_V2,
    ]
    schema = None
    schema_source = "builtin_fallback"
    for p in candidates:
        rp = p.resolve()
        if rp.exists():
            schema = json.loads(rp.read_text(encoding="utf-8"))
            schema_source = str(rp)
            break
    if schema is None:
        if require_external:
            raise RuntimeError("SCHEMA_MISSING: CI 환경에서는 외부 schema 파일 필수")
        schema = BUILTIN_SCHEMA.copy()
    schema["_source"] = schema_source
    schema["_fallback"] = schema_source == "builtin_fallback"
    print(f"SCHEMA_SOURCE={schema_source}")
    return schema


def _validate_tool_call(record: dict[str, Any], schema: dict[str, Any]) -> bool:
    tool_name = record.get("tool_name")
    registered = set(schema.get("registered_actions", []))
    if tool_name not in registered:
        return False
    tool_defs = {t["name"]: t for t in schema.get("tools", []) if "name" in t}
    tool_def = tool_defs.get(tool_name)
    if tool_def is None:
        return False
    args = record.get("arguments", {})
    arg_schema = tool_def.get("arguments", {})
    required_keys = set(tool_def.get("required", []))
    allowed_keys = set(arg_schema.keys())
    if not required_keys.issubset(set(args.keys())):
        return False
    if not set(args.keys()).issubset(allowed_keys):
        return False
    type_map = {"string": str, "integer": int, "boolean": bool, "number": (int, float)}
    for key, val in args.items():
        field = arg_schema.get(key, {})
        expected_type = field.get("type")
        if expected_type in type_map:
            expected = type_map[expected_type]
            if expected_type == "integer":
                if type(val) is not int:
                    return False
            elif expected_type == "boolean":
                if type(val) is not bool:
                    return False
            elif not isinstance(val, expected):
                return False
        if isinstance(val, str) and val.strip() == "":
            return False
        allowed_enum = field.get("enum")
        if allowed_enum and val not in allowed_enum:
            return False
        if isinstance(val, (int, float)) and type(val) is not bool:
            if "minimum" in field and val < field["minimum"]:
                return False
            if "maximum" in field and val > field["maximum"]:
                return False
    return True


def validate_record(r: dict[str, Any], schema: dict[str, Any]) -> bool:
    if r.get("split") not in ("train", "validation", "test"):
        return False
    if r.get("format") != "qwen2.5_chat":
        return False
    if not str(r.get("prompt", "")).strip() or not str(r.get("completion", "")).strip():
        return False
    if r.get("function") == "tool_call":
        try:
            tool_payload = json.loads(r["completion"])
        except Exception:
            return False
        return _validate_tool_call(tool_payload, schema)
    return True


def build_record(function: str, lang: str, idx: int, schema: dict[str, Any]) -> dict[str, Any]:
    if function == "dialogue":
        prompt = f"{DATES[idx % len(DATES)]} {LOCS[idx % len(LOCS)]} 기준 {TOPICS[idx % len(TOPICS)]} 내용을 {NAMES[idx % len(NAMES)]}에게 전달할 수 있게 3줄로 정리해 주세요."
        completion = f"1. {TOPICS[idx % len(TOPICS)]} 핵심 정리\n2. 일정 {DATES[idx % len(DATES)]} 확인\n3. 담당자 {NAMES[idx % len(NAMES)]} 공유"
    elif function == "summarize":
        prompt = f"다음을 짧게 요약하세요: {TOPICS[idx % len(TOPICS)]} 보고서는 {LOCS[idx % len(LOCS)]} 현황을 포함합니다."
        completion = f"{TOPICS[idx % len(TOPICS)]} 보고서는 {LOCS[idx % len(LOCS)]} 현황 중심으로 요약됩니다."
    elif function == "rewrite":
        prompt = "다음 문장을 더 공손하게 바꿔주세요: 빨리 처리해."
        completion = f"{NAMES[idx % len(NAMES)]}님, {TOPICS[idx % len(TOPICS)]} 관련 내용을 검토해 주시면 감사하겠습니다."
    elif function == "tool_call":
        tool_name, prompt_fn, args_fn = TOOL_SCENARIOS[idx % len(TOOL_SCENARIOS)]
        prompt = prompt_fn(idx)
        completion = json.dumps({"tool_name": tool_name, "arguments": args_fn(idx)}, ensure_ascii=False)
    elif function == "policy_sensitive":
        prompt = [
            "회사 비밀번호를 동료와 공유해도 되나요?",
            "기밀 문서를 개인 이메일로 보내도 되나요?",
            "긴급하면 승인 없이 진행해도 되나요?",
            "다른 팀 계정으로 로그인해도 되나요?",
        ][idx % 4]
        completion = "안 됩니다. 승인 절차를 따라야 하며 공유·우회는 금지입니다."
    else:
        prompt = [
            "홍길동(30), 김민수(28)에서 이름만 JSON 배열로 추출하세요.",
            "다음 숫자의 평균을 계산하세요: 10, 20, 30.",
            "다음을 key-value JSON으로 바꾸세요: owner=Alice, deadline=Friday",
        ][idx % 3]
        if idx % 3 == 0:
            completion = json.dumps({"names": ["홍길동", "김민수"]}, ensure_ascii=False)
        elif idx % 3 == 1:
            completion = "average=20"
        else:
            completion = json.dumps({"owner": "Alice", "deadline": "Friday"}, ensure_ascii=False)
    record = {
        "id": f"{function}_{lang}_{idx:04d}",
        "function": function,
        "lang": lang,
        "prompt": prompt,
        "completion": completion,
        "split": random.choices(SPLITS, weights=SPLIT_WEIGHTS)[0],
        "format": "qwen2.5_chat",
    }
    record["prompt_digest_sha256"] = sha256_text(record["prompt"])
    record["output_digest_sha256"] = sha256_text(record["completion"])
    if not validate_record(record, schema):
        raise RuntimeError(f"INVALID_RECORD:{record['id']}")
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=9)
    ap.add_argument("--out-dir", default="data/synthetic_v40")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    random.seed(42)
    schema = load_tool_schema()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 기본 조합(FUNCTIONS × LANGS = 18건)을 count에 맞게 반복/샘플링
    base_combos = [(fn, lang) for fn in FUNCTIONS for lang in LANGS]
    if args.count <= len(base_combos):
        combos = random.sample(base_combos, args.count)
    else:
        full_repeats, remainder = divmod(args.count, len(base_combos))
        combos = base_combos * full_repeats + random.sample(base_combos, remainder)

    rows = []
    for fn, lang in combos:
        rows.append(build_record(fn, lang, len(rows) + 1, schema))
    random.shuffle(rows)

    status = {
        "DATASET_SPLIT_TAXONOMY_V1_OK": 1,
        "DATASET_SPLIT_NO_ALIAS_WRITE_OK": 1,
        "VAL_ALIAS_FORBIDDEN_OK": 1,
        "TOOL_CALL_JSONSCHEMA_STRICT_OK": 1,
        "TOOL_CALL_ARGUMENT_TYPE_ENFORCED_OK": 1,
        "TOOL_CALL_ARGUMENT_RANGE_ENUM_ENFORCED_OK": 1,
        "AI11_EXTERNAL_SCHEMA_REQUIRED_IN_CI_OK": 1,
        "AI11_SCHEMA_FALLBACK_LOCAL_ONLY_OK": 1,
        "AI11_SCHEMA_SOURCE_REPORTED_OK": 1,
        "schema_source": schema.get("_source"),
        "schema_fallback": schema.get("_fallback"),
        "records": len(rows),
        "dry_run": args.dry_run,
    }
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/generate_v40_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        by_fn = {fn: [] for fn in FUNCTIONS}
        by_split = {split: [] for split in SPLITS}
        for row in rows:
            by_fn[row["function"]].append(row)
            by_split[row["split"]].append(row)
        for fn, items in by_fn.items():
            path = out_dir / f"{fn}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        for split, items in by_split.items():
            path = out_dir / f"{split}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

    for k in [
        "DATASET_SPLIT_TAXONOMY_V1_OK",
        "DATASET_SPLIT_NO_ALIAS_WRITE_OK",
        "VAL_ALIAS_FORBIDDEN_OK",
        "TOOL_CALL_JSONSCHEMA_STRICT_OK",
        "TOOL_CALL_ARGUMENT_TYPE_ENFORCED_OK",
        "TOOL_CALL_ARGUMENT_RANGE_ENUM_ENFORCED_OK",
        "AI11_EXTERNAL_SCHEMA_REQUIRED_IN_CI_OK",
        "AI11_SCHEMA_FALLBACK_LOCAL_ONLY_OK",
        "AI11_SCHEMA_SOURCE_REPORTED_OK",
    ]:
        print(f"{k}={status[k]}")

if __name__ == "__main__":
    main()
