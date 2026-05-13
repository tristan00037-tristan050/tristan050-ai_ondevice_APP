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


# ── PR #705 P2-A 정정 회귀 (3건) — use_final_gold 시 fail-closed ─────────

def _annot_pair_with_final_gold(final_gold: dict) -> dict:
    """annotator_a/b 동일 라벨 + 임의 final_gold 부착."""
    A = {"id": "a", "labeled_at": "t",
         "intent_type": "REQUEST", "deadline_type": "NONE",
         "auto_apply_allowed": False}
    B = {"id": "b", "labeled_at": "t",
         "intent_type": "REQUEST", "deadline_type": "NONE",
         "auto_apply_allowed": False}
    return {"sample_id": "card1_999900",
            "annotator_a": A, "annotator_b": B,
            "final_gold":  final_gold}


def test_compute_agreement_fails_when_final_gold_intent_type_missing(tmp_path):
    """use_final_gold=True + final_gold.intent_type 누락 → fail-closed."""
    item = _annot_pair_with_final_gold({"deadline_type": "NONE",
                                        "auto_apply_allowed": False,
                                        "finalized_at": "t"})
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p), "--use-final-gold")
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "FINAL_GOLD_FIELD_MISSING"


def test_compute_agreement_fails_when_final_gold_deadline_type_missing(tmp_path):
    item = _annot_pair_with_final_gold({"intent_type": "REQUEST",
                                        "auto_apply_allowed": False,
                                        "finalized_at": "t"})
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p), "--use-final-gold")
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "FINAL_GOLD_FIELD_MISSING"


def test_compute_agreement_fails_when_final_gold_auto_apply_missing(tmp_path):
    item = _annot_pair_with_final_gold({"intent_type": "REQUEST",
                                        "deadline_type": "NONE",
                                        "finalized_at": "t"})
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p), "--use-final-gold")
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "FINAL_GOLD_FIELD_MISSING"
