"""단계 6.5.5 Day 3 — compute_agreement 강화 단위 테스트 (3건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parents[2]
GATE  = ROOT / "scripts" / "evalset" / "compute_agreement.py"
PY    = sys.executable

# Cohen's kappa 함수 직접 import 테스트도 함께
sys.path.insert(0, str(ROOT / "scripts" / "evalset"))
from compute_agreement import cohen_kappa   # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def test_compute_agreement_from_annotator_fields(tmp_path):
    """annotator_a/b 필드에서 직접 페어 추출 (legacy sample_id 페어 X)."""
    A = {"id": "a", "labeled_at": "2026-05-13T10:00:00Z"}
    B = {"id": "b", "labeled_at": "2026-05-13T10:30:00Z"}

    def sample(sid, a_intent, b_intent, a_dt="NONE", b_dt="NONE",
               a_aa=False, b_aa=False):
        return {
            "sample_id": sid,
            "annotator_a": {**A, "intent_type": a_intent,
                            "deadline_type": a_dt, "auto_apply_allowed": a_aa},
            "annotator_b": {**B, "intent_type": b_intent,
                            "deadline_type": b_dt, "auto_apply_allowed": b_aa},
        }

    items = [
        sample("card1_000001", "REQUEST", "REQUEST"),
        sample("card1_000002", "REPORT",  "REPORT"),
        sample("card1_000003", "REQUEST", "REPORT"),   # 불일치 1건
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))
    # 2/3 = 0.667 → intent threshold 0.85 미달 → fail
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fields"]["intent_type"]["source"]       == "annotator_fields"
    assert out["fields"]["intent_type"]["total_pairs"]  == 3
    assert out["fields"]["intent_type"]["agreed_pairs"] == 2
    assert "kappa" in out["fields"]["intent_type"]


def test_compute_agreement_cohen_kappa_calculation():
    """Cohen's kappa 자체 계산 검증."""
    # 완전 일치 → kappa=1.0
    assert cohen_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]) == 1.0
    # 완전 불일치 + 균형 → kappa 음수
    k_neg = cohen_kappa(["A", "B"], ["B", "A"])
    assert k_neg < 0.0
    # 부분 일치 — 두 클래스, 둘 다 같은 marginal
    k_partial = cohen_kappa(
        ["A", "A", "B", "B", "A"],
        ["A", "B", "A", "B", "A"],
    )
    # observed=3/5=0.6, expected p_e for balanced ≈ 0.5 → kappa = (0.6-0.5)/(1-0.5)=0.2
    assert 0.0 < k_partial < 0.5


def test_compute_agreement_handles_missing_annotator_b(tmp_path):
    """annotator_b 누락 시 그 sample 은 pair 에서 제외 (legacy fallback X)."""
    item = {
        "sample_id": "card1_000001",
        "annotator_a": {"id": "a", "labeled_at": "2026-05-13T10:00:00Z",
                        "intent_type": "REQUEST",
                        "deadline_type": "NONE",
                        "auto_apply_allowed": False},
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    out = json.loads(res.stdout.strip().splitlines()[-1])
    # annotator_b 없으니 페어 미수집. legacy fallback 도 sample_id 1건이라 페어 X.
    assert out["fields"]["intent_type"]["total_pairs"] == 0
    assert out["fail_class"] == "NO_COMPARABLE_PAIRS"


# ── PR #706 P1 정정 회귀 (3건) — annotator_b 가드 분리 ─────────────────

def _gold_v1_minimal(sid: str, intent: str) -> dict:
    """annotator_a + final_gold 만 있는 gold_v1 row (annotator_b 없음)."""
    return {
        "sample_id": sid,
        "annotator_a": {"id": "a", "labeled_at": "t",
                        "intent_type": intent,
                        "deadline_type": "NONE",
                        "auto_apply_allowed": False},
        "final_gold": {
            "intent_type":         intent,
            "deadline_type":       "NONE",
            "auto_apply_allowed":  False,
            "finalized_at":        "t",
        },
    }


def test_compute_agreement_use_final_gold_works_without_annotator_b(tmp_path):
    """gold_v1 row(annotator_a + final_gold만 있음) — use_final_gold 모드에서 정상 처리."""
    items = [_gold_v1_minimal("card1_300001", "REQUEST"),
             _gold_v1_minimal("card1_300002", "REPORT")]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--use-final-gold")
    # 정정 전엔 over-blocking 으로 NO_COMPARABLE_PAIRS 가 발생했음.
    # 정정 후: a_list/b_list 둘 다 2건 수집 → ok=True.
    assert res.returncode == 0, f"unexpected fail: {res.stdout}"
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["fields"]["intent_type"]["total_pairs"] == 2


def test_compute_agreement_default_mode_requires_annotator_b(tmp_path):
    """일반 모드(--use-final-gold 미지정)는 annotator_b 필수 — 기존 로직 유지."""
    items = [_gold_v1_minimal("card1_300003", "REQUEST")]   # annotator_b 없음
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))   # use_final_gold 미지정
    # legacy fallback 도 sample_id 1건이라 페어 X → NO_COMPARABLE_PAIRS
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "NO_COMPARABLE_PAIRS"


def test_compute_agreement_use_final_gold_only_annotator_a_and_final_gold(tmp_path):
    """100% gold_v1 영역 (annotator_b 전혀 없음) — use_final_gold 정상 처리."""
    items = [
        _gold_v1_minimal(f"card1_30{i:04d}", "REQUEST" if i % 2 else "REPORT")
        for i in range(1, 11)
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--use-final-gold")
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    # 모든 row 가 a==final_gold 이므로 합의도 1.0
    assert out["fields"]["intent_type"]["total_pairs"] == 10
    assert out["fields"]["intent_type"]["rate"] == 1.0
