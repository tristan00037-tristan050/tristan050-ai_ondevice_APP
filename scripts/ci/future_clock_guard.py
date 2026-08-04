#!/usr/bin/env python3
"""미래-시계 CI 가드 (future-clock guard).

목적
----
시험 픽스처에 하드코딩된 만료일(예: 2026-12-31)이 ``real now`` 와 비교되면,
그 날짜가 실제로 지나는 순간 시험 결과가 뒤집혀 저장소 전체가 막힌다
(2026-08-01 사고). 이 가드는 그런 "시한폭탄"을 **미리** 드러낸다.

원리
----
같은 시험을 두 번 돌린다.
  1) real now
  2) far-future (기본 2027-06-01) — ``_utc_now`` 를 미래로 주입
결과가 달라진(‑real 통과 / future 실패) 시험 = 시한폭탄.

``now`` 를 주입하는 시험은 미래에서도 결과가 같으므로 **잡히지 않는다**(거짓양성 0).

동시에 pytest 플러그인으로도 동작한다(``-p scripts.ci.future_clock_guard``):
env ``BUTLER_FUTURE_CLOCK`` 이 설정되면 autouse fixture 가
``sys.modules`` 안 모든 ``butler_pc_core.*`` 모듈의 ``_utc_now`` 를 미래로 패치한다.

SANITY
------
판정 전에, 미래 시계가 **실제 만료 검사에 도달**하는지 in-process 로 증명한다.
증명하지 못하면(주입이 안 닿으면) 가드는 통과가 아니라 **오류(exit 3)** 로 멈춘다.
"시험이 안 도는데 통과로 읽는 것"을 막기 위함이다.

허용목록(allowlist)
-------------------
현재 알려진 시한폭탄 6건(3파일)은 ``future_clock_allowlist.txt`` 에 baseline 으로
기록한다. 가드는 **허용목록에 없는 새 시한폭탄**이 나타나면 FAIL 한다.
(이 6건을 고치는 것은 별도 지시 — 가드가 먼저다.)
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

# ── pytest 플러그인 부분 ────────────────────────────────────────────────
_ENV = "BUTLER_FUTURE_CLOCK"


def _fake_now():
    raw = os.environ.get(_ENV)
    if not raw:
        return None
    return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _patch_all_utc_now(fake, monkeypatch):
    """import 된 모든 butler_pc_core 모듈의 _utc_now 를 미래로 고정."""
    patched = []
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        name = getattr(mod, "__name__", "") or ""
        if not name.startswith("butler_pc_core"):
            continue
        if hasattr(mod, "_utc_now"):
            monkeypatch.setattr(mod, "_utc_now", lambda: fake, raising=False)
            patched.append(name)
    return patched


try:
    import pytest

    @pytest.fixture(autouse=True)
    def _future_clock(monkeypatch):  # noqa: PT004 (autouse, 반환값 불필요)
        fake = _fake_now()
        if fake is not None:
            _patch_all_utc_now(fake, monkeypatch)
        yield
except ImportError:  # pytest 없이 러너만 import 될 때
    pass


# ── 러너 부분 ──────────────────────────────────────────────────────────
FUTURE_DEFAULT = "2027-06-01T00:00:00Z"
DEFAULT_SCOPE = "tests/connect_loop"
ALLOWLIST = os.path.join(os.path.dirname(__file__), "future_clock_allowlist.txt")


def _sanity(fake):
    """미래 시계가 실제 만료 검사(RETENTION_EXPIRED)에 도달함을 in-process 증명.

    - real now  로 도달  → 만료 아님 (drop_reason != RETENTION_EXPIRED)
    - future now 로 도달 → RETENTION_EXPIRED
    두 조건이 아니면 주입이 실패한 것이므로 가드를 멈춘다.
    """
    import hashlib

    from butler_pc_core.connect_loop import learning_candidate_gate as g

    def _d(v):
        return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()

    usage_log = {
        "log_id": "sanity-1", "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-sanity", "device_id_digest": _d("dev"),
        "tenant_id_digest": _d("t"), "department_id_digest": _d("dep"),
        "request_digest": _d("req"), "intent_label": "memory_search",
        "box_id": "helper1", "endpoint": "POST /v1/helpers/1/search",
        "routing_confidence": 0.92, "integration_mode": "real",
        "real_validation_done": True, "result_digest": _d("res"),
        "source_digests": [_d("s")], "policy_decision": "allow",
        "policy_reason_code": "OK", "latency_ms": 10.0,
        "external_send_zero": True, "raw_text_logged": False,
        "learning_candidate": True, "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.usage_accumulator",
        "schema_hash": _d("schema"), "schema_version": "usage_log.v1.1",
    }
    envelope = {
        "learning_allowed": True, "tenant_scope": "device",
        "retention_days": 30, "expires_at": "2026-12-31T00:00:00Z",
        "reason_code": "LEARNING_ALLOWED_SANITIZED",
    }
    bundle = g.ApprovedRefBundle(
        approved_text_ref="vault://sanity", approved_text_digest=_d("a"),
        sanitized_summary_digest=_d("s"), runtime_text_for_dlp="정제 요약(PII 없음)",
    )
    dlp = {"passed": True, "pii_detected": False, "secret_detected": False, "policy_violation": False}
    cand = g.select_learning_candidates([usage_log])[0]
    gi = g.build_learning_gate_input(cand, bundle, envelope, dlp_result=dlp)

    real = g.create_learning_event_result(gi, now=_dt.datetime.now(_dt.timezone.utc))
    fut = g.create_learning_event_result(gi, now=fake)
    real_ok = real.drop_reason != "RETENTION_EXPIRED"
    fut_expired = fut.drop_reason == "RETENTION_EXPIRED"
    return real_ok, fut_expired, real.drop_reason, fut.drop_reason


def _run_pytest(scope, junit, future):
    import subprocess

    env = dict(os.environ)
    if future:
        env[_ENV] = future
    else:
        env.pop(_ENV, None)
    # 자기 자신을 플러그인으로 로드
    plugin = "scripts.ci.future_clock_guard"
    cmd = [sys.executable, "-m", "pytest", scope, "-p", plugin,
           "-q", "-p", "no:cacheprovider", "--junitxml", junit, "--tb=no"]
    subprocess.run(cmd, env=env, cwd=os.getcwd(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _failed_set(junit):
    import xml.etree.ElementTree as ET

    failed = set()
    tree = ET.parse(junit)
    for tc in tree.iter("testcase"):
        nid = f"{tc.get('classname')}::{tc.get('name')}"
        if any(c.tag in ("failure", "error") for c in tc):
            failed.add(nid)
    return failed


def _nodeids(junit):
    import xml.etree.ElementTree as ET

    ids = set()
    for tc in ET.parse(junit).iter("testcase"):
        ids.add(f"{tc.get('classname')}::{tc.get('name')}")
    return ids


def _load_allowlist():
    if not os.path.exists(ALLOWLIST):
        return set()
    out = set()
    with open(ALLOWLIST, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def main(argv):
    import argparse

    ap = argparse.ArgumentParser(description="future-clock CI guard")
    ap.add_argument("--scope", default=DEFAULT_SCOPE)
    ap.add_argument("--future", default=FUTURE_DEFAULT)
    ap.add_argument("--write-allowlist", action="store_true",
                    help="탐지된 집합을 allowlist 로 기록(초기 baseline 생성용)")
    args = ap.parse_args(argv)

    fake = _dt.datetime.fromisoformat(args.future.replace("Z", "+00:00"))

    # repo 루트를 import 경로에 추가(러너 직접 실행 시 conftest 미개입)
    root = os.getcwd()
    if root not in sys.path:
        sys.path.insert(0, root)

    # 1) SANITY — 미래 시계가 실제 만료 검사에 도달하는가
    real_ok, fut_expired, dr_real, dr_fut = _sanity(fake)
    print(f"[SANITY] real_now→not_expired={real_ok} (drop={dr_real!r}) · "
          f"future_now→RETENTION_EXPIRED={fut_expired} (drop={dr_fut!r})")
    if not (real_ok and fut_expired):
        print("[SANITY] ✗ 미래 시계가 만료 검사에 도달하지 못함 — 가드 신뢰 불가. EXIT 3")
        return 3
    print("[SANITY] ✓ 미래 시계가 실제 만료 검사에 도달함")

    # 2) 두 번 실행 (real / future)
    import tempfile

    d = tempfile.mkdtemp(prefix="futclock_")
    jr, jf = os.path.join(d, "real.xml"), os.path.join(d, "future.xml")
    print(f"[RUN] real now    : pytest {args.scope}")
    _run_pytest(args.scope, jr, future="")
    print(f"[RUN] future ({args.future}) : pytest {args.scope}")
    _run_pytest(args.scope, jf, future=args.future)

    collected = _nodeids(jr)
    real_fail = _failed_set(jr)
    fut_fail = _failed_set(jf)
    detected = sorted((fut_fail - real_fail))  # real 통과 & future 실패 = 시한폭탄
    print(f"[RUN] collected={len(collected)} · real_fail={len(real_fail)} · "
          f"future_fail={len(fut_fail)} · detected(flip)={len(detected)}")

    if args.write_allowlist:
        with open(ALLOWLIST, "w", encoding="utf-8") as fh:
            fh.write("# future-clock 가드 baseline — 알려진 시한폭탄(고치기는 별도 지시)\n")
            fh.write(f"# 생성 scope={args.scope} future={args.future}\n")
            for n in detected:
                fh.write(n + "\n")
        print(f"[WRITE] allowlist {len(detected)}건 기록 → {ALLOWLIST}")
        for n in detected:
            print("   -", n)
        return 0

    allow = _load_allowlist()
    new = [n for n in detected if n not in allow]
    fixed = [n for n in allow if n not in detected]

    print(f"[JUDGE] detected={len(detected)} allowlist={len(allow)} "
          f"new={len(new)} fixed(stale)={len(fixed)}")
    for n in detected:
        tag = "NEW★" if n in new else "known"
        print(f"   [{tag}] {n}")

    if new:
        print("\n[FAIL] 허용목록에 없는 새 시한폭탄 발견 — real now 에 의존하는 시험을 "
              "고치거나 now 를 주입하십시오. EXIT 1")
        return 1
    if fixed:
        print("\n[WARN] allowlist 에 있으나 더는 탐지되지 않는 항목(고쳐진 듯) — "
              "allowlist 에서 제거하십시오:")
        for n in fixed:
            print("   -", n)
        return 2
    print("\n[OK] 새 시한폭탄 없음(알려진 baseline 과 일치). EXIT 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
