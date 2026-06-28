#!/usr/bin/env python3
"""Static verification for Butler model-path role separation (PR #831).

CI 재발 방지용. 자유대화(4B)와 박스3(1.7B) 모델 역할이 코드에서 분리됐는지,
금지 패턴(박스3를 BUTLER_MODEL_PATH에 주입 / 상호 fallback)이 재발했는지 검출.
이 파일 자신은 FORBIDDEN 문자열을 담으므로 검사 대상에서 제외(self-오탐 방지).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

FORBIDDEN_LIB = [
    "BUTLER_MODEL_PATH_ENV, model_path",
    "butler_model_path = box3_v9_model_path",
    "box3_v9_model_path = butler_model_path",
]
REQUIRED_LIB = [
    "push_free_chat_resource_env",
    "validate_model_path_invariants",
    "qwen3-4b-q4_k_m.gguf",
    "butler-1.7b-v9-2-r2b-q4_k_m.gguf",
]
REQUIRED_IDENTITY = [
    "assert_main_not_box3",
    "model_path_conflict_reason",
    "model_path_digest",
    "model_role",
    "model_family",
    "is_box3_model_path",
]
REQUIRED_SIDECAR = [
    "/api/model/status",
    "model_path_conflict",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    lib = repo / "butler-desktop" / "src-tauri" / "src" / "lib.rs"
    sidecar = repo / "butler_sidecar.py"
    identity = repo / "butler_pc_core" / "inference" / "model_identity.py"
    failures: list[str] = []
    for f, label in [(lib, "lib.rs"), (sidecar, "butler_sidecar.py"), (identity, "model_identity.py")]:
        if not f.exists():
            failures.append(f"missing {label}")
    lib_text, side_text, id_text = _read(lib), _read(sidecar), _read(identity)
    for pat in FORBIDDEN_LIB:
        if pat in lib_text:
            failures.append(f"forbidden pattern in lib.rs: {pat}")
    for pat in REQUIRED_LIB:
        if pat not in lib_text:
            failures.append(f"required lib.rs pattern missing: {pat}")
    for pat in REQUIRED_IDENTITY:
        if pat not in id_text:
            failures.append(f"required model_identity.py pattern missing: {pat}")
    for pat in REQUIRED_SIDECAR:
        if pat not in side_text:
            failures.append(f"required sidecar pattern missing: {pat}")
    result = {"ok": not failures, "failures": failures}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
