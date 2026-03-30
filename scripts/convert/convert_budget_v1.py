from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BUDGET = {
    "mnn_size_mb_max": 3072,
    "mnn_size_mb_target": 1024,
    "ort_size_mb_max": 3072,
    "first_token_sec_max": 5.0,
    "throughput_tokens_per_sec_min": 10,
    "load_time_sec_max": 10.0,
}


@dataclass
class BudgetCheckResult:
    mnn_size_mb: float
    mnn_size_ok: bool
    mnn_target_ok: bool
    ort_size_mb: float | None
    ort_size_ok: bool | None
    file_budget_passed: bool
    fail_reasons: list[str]
    first_token_sec: float | None = None
    throughput_tps: float | None = None
    load_time_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 ** 2)


def check_budget(
    mnn_path: str,
    ort_path: str | None = None,
    dry_run: bool = False,
) -> BudgetCheckResult:
    if dry_run:
        return BudgetCheckResult(
            mnn_size_mb=0.0,
            mnn_size_ok=True,
            mnn_target_ok=True,
            ort_size_mb=None,
            ort_size_ok=None,
            file_budget_passed=True,
            fail_reasons=[],
        )

    fail_reasons: list[str] = []
    mnn_file = Path(mnn_path)
    if not mnn_file.exists():
        fail_reasons.append("MNN_FILE_MISSING")
        mnn_size_mb = 0.0
        mnn_size_ok = False
        mnn_target_ok = False
    else:
        mnn_size_mb = _size_mb(mnn_file)
        mnn_size_ok = mnn_size_mb <= BUDGET["mnn_size_mb_max"]
        mnn_target_ok = mnn_size_mb <= BUDGET["mnn_size_mb_target"]
        if not mnn_size_ok:
            fail_reasons.append(
                f"MNN_SIZE_EXCEED:{mnn_size_mb:.0f}MB>{BUDGET['mnn_size_mb_max']}MB"
            )
        elif not mnn_target_ok:
            print(
                f"WARN: MNN 크기 목표 초과 ({mnn_size_mb:.0f}MB > {BUDGET['mnn_size_mb_target']}MB 권장)"
            )

    ort_size_mb: float | None = None
    ort_size_ok: bool | None = None
    if ort_path:
        ort_file = Path(ort_path)
        if ort_file.exists():
            ort_size_mb = _size_mb(ort_file)
            ort_size_ok = ort_size_mb <= BUDGET["ort_size_mb_max"]
            if not ort_size_ok:
                fail_reasons.append(
                    f"ORT_SIZE_EXCEED:{ort_size_mb:.0f}MB>{BUDGET['ort_size_mb_max']}MB"
                )
        else:
            ort_size_ok = False
            fail_reasons.append("ORT_FILE_MISSING")

    file_budget_passed = len(fail_reasons) == 0
    if file_budget_passed:
        print("FILE_BUDGET_OK=1")
    return BudgetCheckResult(
        mnn_size_mb=round(mnn_size_mb, 1),
        mnn_size_ok=mnn_size_ok,
        mnn_target_ok=mnn_target_ok,
        ort_size_mb=round(ort_size_mb, 1) if ort_size_mb is not None else None,
        ort_size_ok=ort_size_ok,
        file_budget_passed=file_budget_passed,
        fail_reasons=fail_reasons,
    )


def get_budget_spec() -> dict[str, Any]:
    return dict(BUDGET)
