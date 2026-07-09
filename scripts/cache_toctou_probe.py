#!/usr/bin/env python3
"""Box3 approval cache/TOCTOU probe (v1.2 §8 증거).

증명 항목(meta-only, 판정만):
- 승인 전용 identity 는 module-level cache 를 신뢰하지 않고 매번 full rehash 한다.
  (동일 경로 파일 내용 교체 시 model_digest 가 바뀐다.)
- size/mtime 을 보존한 채 내용만 바꾼 교체도 model_digest 변화로 탐지된다.
- symlink 모델 경로는 거부된다.
출력: CACHE_TOCTOU_PROBE_OK=1 (모든 항목 통과) / =0 + REASON.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.cards.box3.model_identity import (
    get_box3_model_identity_for_approval,
    hash_model_file_for_security,
)


def _probe() -> None:
    tmp = Path(tempfile.mkdtemp())
    model = tmp / "box3.gguf"
    model.write_bytes(b"CONTENT-A" * 4096)
    os.environ["BUTLER_BOX3_V9_Q4_MODEL_PATH"] = str(model)

    first = get_box3_model_identity_for_approval()
    assert first is not None, "IDENTITY_UNAVAILABLE"

    # size/mtime 보존 교체: 동일 길이 다른 내용 + 원래 mtime 복원.
    st = model.stat()
    replacement = b"CONTENT-B" * 4096
    assert len(replacement) == st.st_size, "PROBE_SETUP_SIZE"
    model.write_bytes(replacement)
    os.utime(model, ns=(st.st_atime_ns, st.st_mtime_ns))

    second = get_box3_model_identity_for_approval()
    assert second is not None, "IDENTITY_UNAVAILABLE"

    # cache 를 신뢰했다면 동일 digest 를 반환했을 것 — full rehash 이므로 달라야 한다.
    if second.model_digest == first.model_digest:
        raise AssertionError("CACHE_STALE_BYPASS_DETECTED")

    # symlink deny
    link = tmp / "link.gguf"
    link.symlink_to(model)
    try:
        hash_model_file_for_security(str(link))
        raise AssertionError("SYMLINK_NOT_DENIED")
    except ValueError as exc:
        if str(exc) != "MODEL_PATH_SYMLINK_DENIED":
            raise AssertionError("SYMLINK_WRONG_REASON") from exc


def main() -> int:
    try:
        _probe()
    except AssertionError as exc:
        print("CACHE_TOCTOU_PROBE_OK=0")
        print(f"REASON={exc}")
        return 1
    print("CACHE_TOCTOU_PROBE_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
