"""evaluator.py — semantic_mapping 파이프라인 배치 평가 + 정확도 보고."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .contracts import SourceField, ValueType
from .pipeline import map_fields
from .slot_schema import SLOT_BY_ID, TARGET_SLOTS


@dataclass
class SlotMetric:
    total: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 1.0


@dataclass
class FailureRecord:
    case_id: str
    category: str
    slot_id: str
    expected_label: Optional[str]   # None → expected unmapped
    actual_label: Optional[str]     # None → was unmapped
    confidence: float


@dataclass
class EvalReport:
    total_cases: int
    total_expected_mappings: int
    correct_mappings: int

    overall_mapping_accuracy: float

    slot_accuracy: dict[str, float]          # slot_id → accuracy
    contact_mapping_accuracy: float
    money_mapping_accuracy: float            # budget slot accuracy

    date_range_confusion: float              # % DATE/DATE_RANGE fields → wrong slot
    slot_collapse_count: int                 # cases with 2+ sources to same slot
    confidence_calibration_error: float      # mean |confidence - is_correct|

    category_accuracy: dict[str, float]      # category → accuracy
    failures: list[FailureRecord]


def _make_source_fields(raw: list[dict]) -> list[SourceField]:
    return [
        SourceField(
            label=f["label"],
            value=f["value"],
            raw_text=f"{f['label']}: {f['value']}",
        )
        for f in raw
    ]


def run_evaluation(dataset_path: str | Path) -> EvalReport:
    """JSON 데이터셋 50건 평가 → EvalReport 반환."""
    dataset: list[dict] = json.loads(Path(dataset_path).read_text(encoding="utf-8"))

    slot_metrics: dict[str, SlotMetric] = {s.slot_id: SlotMetric() for s in TARGET_SLOTS}
    contact_metric = SlotMetric()
    budget_metric  = SlotMetric()
    failures: list[FailureRecord] = []
    calibration_errors: list[float] = []
    category_totals: dict[str, int]   = {}
    category_correct: dict[str, int]  = {}
    date_total = 0
    date_wrong = 0
    collapse_count = 0
    total_expected = 0
    total_correct  = 0

    for case in dataset:
        case_id  = case["id"]
        category = case["category"]
        src_fields = _make_source_fields(case["source_fields"])
        expected   = case.get("expected_mappings", {})

        decisions = map_fields(src_fields, TARGET_SLOTS)
        decision_by_slot = {d.target_slot.slot_id: d for d in decisions}

        # Collapse check: any two decisions mapping to same source?
        mapped_labels = [
            d.source_field.label for d in decisions
            if d.mapped and d.source_field is not None
        ]
        if len(mapped_labels) != len(set(mapped_labels)):
            collapse_count += 1

        for slot_id, exp_label in expected.items():
            total_expected += 1
            category_totals[category] = category_totals.get(category, 0) + 1
            d = decision_by_slot.get(slot_id)
            if d is None:
                continue

            actual_label: Optional[str] = d.source_field.label if d.mapped else None
            is_correct = (actual_label == exp_label)

            # Calibration error — exp_label이 있는 케이스만 포함
            # null-expected(unmapped 기대) 제외: confidence 없으므로 교정 의미 없음
            if exp_label is not None:
                confidence = d.confidence if d.mapped else 0.0
                calibration_errors.append(abs(confidence - (1.0 if is_correct else 0.0)))

            if is_correct:
                total_correct += 1
                slot_metrics[slot_id].correct += 1
                category_correct[category] = category_correct.get(category, 0) + 1
            else:
                failures.append(FailureRecord(
                    case_id=case_id,
                    category=category,
                    slot_id=slot_id,
                    expected_label=exp_label,
                    actual_label=actual_label,
                    confidence=confidence,
                ))

            slot_metrics[slot_id].total += 1

            if slot_id == "contact":
                contact_metric.total += 1
                if is_correct:
                    contact_metric.correct += 1

            if slot_id == "budget":
                budget_metric.total += 1
                if is_correct:
                    budget_metric.correct += 1

            # DATE/DATE_RANGE confusion: expected mapped to schedule or business_period
            if exp_label is not None and slot_id in ("schedule", "business_period"):
                src = next((f for f in src_fields if f.label == exp_label), None)
                if src and src.detected_type in (ValueType.DATE, ValueType.DATE_RANGE):
                    date_total += 1
                    if not is_correct:
                        date_wrong += 1

    overall_acc = total_correct / total_expected if total_expected else 1.0

    return EvalReport(
        total_cases=len(dataset),
        total_expected_mappings=total_expected,
        correct_mappings=total_correct,
        overall_mapping_accuracy=round(overall_acc, 4),
        slot_accuracy={sid: round(m.accuracy, 4) for sid, m in slot_metrics.items()},
        contact_mapping_accuracy=round(contact_metric.accuracy, 4),
        money_mapping_accuracy=round(budget_metric.accuracy, 4),
        date_range_confusion=round(date_wrong / date_total, 4) if date_total else 0.0,
        slot_collapse_count=collapse_count,
        confidence_calibration_error=round(
            sum(calibration_errors) / len(calibration_errors), 4
        ) if calibration_errors else 0.0,
        category_accuracy={
            cat: round(category_correct.get(cat, 0) / total, 4)
            for cat, total in category_totals.items()
        },
        failures=failures,
    )


def print_report(report: EvalReport) -> None:
    print(f"\n{'='*60}")
    print(f"  semantic_mapping 평가 결과 ({report.total_cases}건)")
    print(f"{'='*60}")
    print(f"  전체 정확도        : {report.overall_mapping_accuracy*100:.1f}%  "
          f"({report.correct_mappings}/{report.total_expected_mappings})")
    print(f"  연락처 정확도      : {report.contact_mapping_accuracy*100:.1f}%")
    print(f"  금액 정확도        : {report.money_mapping_accuracy*100:.1f}%")
    print(f"  날짜 혼동률        : {report.date_range_confusion*100:.1f}%")
    print(f"  슬롯 중복 배정     : {report.slot_collapse_count}건")
    print(f"  신뢰도 교정 오차   : {report.confidence_calibration_error*100:.1f}%")
    print(f"\n  [슬롯별 정확도]")
    for slot_id, acc in report.slot_accuracy.items():
        slot = SLOT_BY_ID[slot_id]
        print(f"    {slot.heading:<12} : {acc*100:.1f}%")
    print(f"\n  [카테고리별 정확도]")
    for cat, acc in report.category_accuracy.items():
        print(f"    {cat:<14} : {acc*100:.1f}%")
    if report.failures:
        print(f"\n  [실패 케이스 {len(report.failures)}건]")
        for f in report.failures:
            exp = f.expected_label or "unmapped"
            act = f.actual_label or "unmapped"
            print(f"    {f.case_id} [{f.category}] {f.slot_id}: "
                  f"expected={exp!r} actual={act!r} conf={f.confidence:.3f}")
    print(f"{'='*60}\n")
