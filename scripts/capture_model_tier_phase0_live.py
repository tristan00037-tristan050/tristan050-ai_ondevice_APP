#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = Path.home() / ".butler" / "audit" / "model_tier_shadow_v1.jsonl"
TOKEN_PATH = Path.home() / ".butler" / "sidecar_token"
RAW_KEYS = frozenset({"runtime_text", "reference_docs", "drafting_request", "draft_text", "input_text"})


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _post(url: str, payload: dict[str, Any], token: str, request_id: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _field_digests(body: bytes) -> dict[str, str]:
    try:
        payload = json.loads(body)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): _digest(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        for key, value in payload.items()
    }


def _leaf_digests(body: bytes) -> dict[str, str]:
    try:
        payload = json.loads(body)
    except Exception:
        return {}
    output: dict[str, str] = {}

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(nested, f"{path}.{key}" if path else str(key))
            return
        if isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, f"{path}[{index}]")
            return
        output[path] = _digest(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )

    visit(payload, "")
    return output


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise ValueError("LIVE_STATUS_INVALID")
    return value


def _cases() -> list[tuple[str, str, dict[str, Any]]]:
    def chat(case_id: str, text: str) -> dict[str, Any]:
        text_digest = _digest(text.encode("utf-8"))
        return {
            "chat_request": {
                "schema_version": "chat_request.v1",
                "request_id": f"req-phase0-{case_id}-001",
                "session_id_digest": _digest(b"phase0-session"),
                "tenant_id_digest": _digest(b"phase0-tenant"),
                "device_id": "device-local-phase0",
                "user_role": "employee",
                "department_id_digest": _digest(b"phase0-department"),
                "text_ref": "device_local_only",
                "text_digest": text_digest,
                "attachments": [],
                "created_at": "2026-07-12T00:00:00Z",
            },
            "runtime": {"runtime_text": text},
        }

    return [
        ("box1_simple", "/v1/router/decide", chat("box1-simple", "지난달 회의 기록을 찾아줘")),
        ("box1_ambiguous", "/v1/router/decide", chat("box1-ambiguous", "이것 좀 적당히 처리해줘")),
        (
            "box3_pass",
            "/v1/cards/3/draft",
            {
                "reference_docs": ["2025년 사무용 책상 50개를 서울시청에 납품했고 계약금액은 3천만 원이다."],
                "drafting_request": "납품 완료 보고서 초안을 작성해줘.",
                "format_hint": "자유형",
            },
        ),
        (
            "box3_review",
            "/v1/cards/3/draft",
            {
                "reference_docs": ["2025년 반려동물 용품 유통 사업을 운영했다."],
                "drafting_request": "근거에 없는 2026년 확정 매출을 포함한 초안을 작성해줘.",
                "format_hint": "자유형",
            },
        ),
    ]


def _audit_rows() -> list[dict[str, Any]]:
    if not AUDIT_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _chip_family() -> str:
    output = subprocess.check_output(["system_profiler", "SPHardwareDataType"], text=True)
    for line in output.splitlines():
        if line.strip().startswith("Chip:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def capture(mode: str, base_url: str, app_executable: Path, output: Path) -> None:
    if mode not in {"off", "on"}:
        raise ValueError("LIVE_CAPTURE_MODE_INVALID")
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    before_status = _get_json(base_url + "/api/model-tier/shadow/status")
    if bool(before_status.get("active")) is (mode == "off"):
        raise ValueError("LIVE_CAPTURE_HOOK_MODE_MISMATCH")
    before_rows = len(_audit_rows())
    case_rows = []
    for case_id, endpoint, payload in _cases():
        status, body = _post(base_url + endpoint, payload, token, f"phase0-live-{case_id}-001")
        case_rows.append(
            {
                "case_id": case_id,
                "http_status": status,
                "response_digest": _digest(body),
                "response_field_digests": _field_digests(body),
                "response_leaf_digests": _leaf_digests(body),
            }
        )
    deadline = time.monotonic() + 5
    while mode == "on" and time.monotonic() < deadline:
        status = _get_json(base_url + "/api/model-tier/shadow/status")
        if status.get("written", 0) >= before_status.get("written", 0) + len(case_rows):
            break
        time.sleep(0.05)
    after_status = _get_json(base_url + "/api/model-tier/shadow/status")
    new_rows = _audit_rows()[before_rows:]
    raw_findings = sum(1 for row in new_rows if set(row) & RAW_KEYS)
    output.write_text(
        json.dumps(
            {
                "schema_version": "butler.model_tier_live_shadow_capture.v1",
                "capture_source": "butler_app_live_http",
                "synthetic": False,
                "mode": mode,
                "chip_family": _chip_family(),
                "app_executable_digest": _digest(app_executable.read_bytes()),
                "cases": case_rows,
                "counter_before": before_status,
                "counter_after": after_status,
                "raw_key_findings": raw_findings,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def merge(off_path: Path, on_path: Path, output: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from butler_pc_core.model_tier.live_evidence import validate_live_shadow_evidence

    off = json.loads(off_path.read_text(encoding="utf-8"))
    on = json.loads(on_path.read_text(encoding="utf-8"))
    if off.get("mode") != "off" or on.get("mode") != "on":
        raise ValueError("LIVE_CAPTURE_PAIR_INVALID")
    if off.get("app_executable_digest") != on.get("app_executable_digest"):
        raise ValueError("LIVE_CAPTURE_APP_DIGEST_MISMATCH")
    off_cases = {row["case_id"]: row for row in off["cases"]}
    on_cases = {row["case_id"]: row for row in on["cases"]}
    cases = [
        {
            "case_id": case_id,
            "hook_off_http_status": off_cases[case_id]["http_status"],
            "hook_on_http_status": on_cases[case_id]["http_status"],
            "hook_off_response_digest": off_cases[case_id]["response_digest"],
            "hook_on_response_digest": on_cases[case_id]["response_digest"],
        }
        for case_id in sorted(off_cases)
    ]
    before = on["counter_before"]
    after = on["counter_after"]
    evidence = {
        "schema_version": "butler.model_tier_live_shadow_evidence.v1",
        "capture_source": "butler_app_live_http",
        "synthetic": False,
        "chip_family": on["chip_family"],
        "app_executable_digest": on["app_executable_digest"],
        "cases": cases,
        "raw_key_findings": on["raw_key_findings"],
        "hook_on_counter_delta": {
            key: int(after.get(key, 0)) - int(before.get(key, 0))
            for key in ("submitted", "written", "dropped", "failures")
        },
    }
    validate_live_shadow_evidence(evidence)
    output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("capture")
    collect.add_argument("--mode", required=True, choices=("off", "on"))
    collect.add_argument("--base-url", default="http://127.0.0.1:8765")
    collect.add_argument("--app-executable", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    combine = subparsers.add_parser("merge")
    combine.add_argument("--off", type=Path, required=True)
    combine.add_argument("--on", type=Path, required=True)
    combine.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.mode, args.base_url, args.app_executable, args.output)
    else:
        merge(args.off, args.on, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
