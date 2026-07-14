from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError


class Stage(StrEnum):
    START = "START"
    IDENTITY_VALIDATED = "IDENTITY_VALIDATED"
    GENERATION_DONE = "GENERATION_DONE"
    PROVISIONAL_QUALITY_DECIDED = "PROVISIONAL_QUALITY_DECIDED"
    GROUNDING_DONE = "GROUNDING_DONE"
    DLP_DONE = "DLP_DONE"
    APPROVAL_POLICY_DONE = "APPROVAL_POLICY_DONE"
    TERMINALIZED = "TERMINALIZED"


_ORDER = list(Stage)
_NO_REPAIR = {
    "IDENTITY_BLOCK", "ASSET_BLOCK", "HARD_POLICY_BLOCK", "DLP_BLOCK", "RUNTIME_ERROR"
}


@dataclass(frozen=True, slots=True)
class TerminalVerdict:
    status: str
    final_gate: str
    fail_class: str | None
    exit_code: int
    repair_count: int
    stage_count: int
    event_digest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "final_gate": self.final_gate,
            "fail_class": self.fail_class,
            "exit_code": self.exit_code,
            "repair_count": self.repair_count,
            "stage_count": self.stage_count,
            "event_digest_sha256": self.event_digest_sha256,
        }


class TerminalDecisionMachine:
    """Single authoritative terminal gate with explicit skipped stages."""

    __slots__ = ("_events", "_stage", "_terminal", "_dlp_passed", "_grounding_passed", "_approval_passed", "_repair_count")

    def __init__(self) -> None:
        self._events: list[dict[str, object]] = []
        self._stage = Stage.START
        self._terminal: TerminalVerdict | None = None
        self._dlp_passed: bool | None = None
        self._grounding_passed: bool | None = None
        self._approval_passed: bool | None = None
        self._repair_count = 0
        self._append(Stage.START, "OBSERVED")

    def advance(self, stage: Stage, *, outcome: str = "PASS") -> None:
        if self._terminal is not None:
            raise GateError(FailClass.EVENT_AFTER_TERMINAL, "ADVANCE_AFTER_FINAL", exit_code=ExitCode.PROTOCOL)
        expected = _ORDER[_ORDER.index(self._stage) + 1]
        if stage is not expected or stage is Stage.TERMINALIZED:
            raise GateError(FailClass.FSM_SEQUENCE_INVALID, "TERMINAL_STAGE_ORDER", exit_code=ExitCode.PROTOCOL)
        if outcome not in {"PASS", "SKIPPED"}:
            raise GateError(FailClass.SCHEMA_INVALID, "STAGE_OUTCOME", exit_code=ExitCode.SCHEMA)
        self._stage = stage
        self._append(stage, outcome)

    def record_grounding(self, passed: bool) -> None:
        self.advance(Stage.GROUNDING_DONE, outcome="PASS" if passed else "SKIPPED")
        self._grounding_passed = passed

    def record_dlp(self, passed: bool) -> None:
        self.advance(Stage.DLP_DONE, outcome="PASS" if passed else "SKIPPED")
        self._dlp_passed = passed

    def record_approval(self, passed: bool) -> None:
        self.advance(Stage.APPROVAL_POLICY_DONE, outcome="PASS" if passed else "SKIPPED")
        self._approval_passed = passed

    def record_repair(self) -> None:
        if self._terminal is not None or self._repair_count >= 1:
            raise GateError(FailClass.FORBIDDEN_REPAIR, "REPAIR_LIMIT", exit_code=ExitCode.PROTOCOL)
        self._repair_count += 1

    def block(self, fail_class: str) -> TerminalVerdict:
        if self._terminal is not None:
            raise GateError(FailClass.FINAL_GATE_COUNT_INVALID, "SECOND_FINAL", exit_code=ExitCode.PROTOCOL)
        if fail_class in _NO_REPAIR and self._repair_count:
            raise GateError(FailClass.FORBIDDEN_REPAIR, "REPAIR_ON_HARD_FAIL", exit_code=ExitCode.PROTOCOL)
        # Every early exit records the unexecuted gates as SKIPPED, ensuring the
        # one terminal event always appears after an explicit DLP stage record.
        while self._stage is not Stage.APPROVAL_POLICY_DONE:
            next_stage = _ORDER[_ORDER.index(self._stage) + 1]
            if next_stage is Stage.GROUNDING_DONE:
                self._grounding_passed = False
            elif next_stage is Stage.DLP_DONE:
                self._dlp_passed = False
            elif next_stage is Stage.APPROVAL_POLICY_DONE:
                self._approval_passed = False
            self.advance(next_stage, outcome="SKIPPED")
        return self._terminalize(status="BLOCKED", fail_class=fail_class, exit_code=ExitCode.PROTOCOL)

    def pass_final(self) -> TerminalVerdict:
        if self._terminal is not None:
            raise GateError(FailClass.FINAL_GATE_COUNT_INVALID, "SECOND_FINAL", exit_code=ExitCode.PROTOCOL)
        if self._stage is not Stage.APPROVAL_POLICY_DONE:
            raise GateError(FailClass.FINAL_BEFORE_DLP, "FINAL_STAGE_EARLY", exit_code=ExitCode.PROTOCOL)
        if self._dlp_passed is not True or self._approval_passed is not True or self._grounding_passed is not True:
            raise GateError(FailClass.TERMINAL_STATUS_MISMATCH, "PASS_WITH_FAILED_GATE", exit_code=ExitCode.PROTOCOL)
        return self._terminalize(status="PASS", fail_class=None, exit_code=ExitCode.PASS)

    def _terminalize(self, *, status: str, fail_class: str | None, exit_code: ExitCode) -> TerminalVerdict:
        self._stage = Stage.TERMINALIZED
        self._append(Stage.TERMINALIZED, status)
        digest = canonical_sha256(self._events)
        self._terminal = TerminalVerdict(
            status=status,
            final_gate="ALLOW" if status == "PASS" else "BLOCK",
            fail_class=fail_class,
            exit_code=int(exit_code),
            repair_count=self._repair_count,
            stage_count=len(self._events),
            event_digest_sha256=digest,
        )
        return self._terminal

    def _append(self, stage: Stage, outcome: str) -> None:
        now = time.monotonic_ns()
        if self._events and now <= int(self._events[-1]["monotonic_ns"]):
            now = int(self._events[-1]["monotonic_ns"]) + 1
        self._events.append({"seq": len(self._events), "stage": stage.value, "outcome": outcome, "monotonic_ns": now})

    @property
    def safe_events(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(event) for event in self._events)


def verify_terminal_evidence(events: list[dict[str, object]], verdict: dict[str, object]) -> None:
    terminal_indices = [index for index, event in enumerate(events) if event.get("stage") == Stage.TERMINALIZED.value]
    if len(terminal_indices) != 1:
        raise GateError(FailClass.FINAL_GATE_COUNT_INVALID, "TERMINAL_EVENT_COUNT", exit_code=ExitCode.PROTOCOL)
    terminal_index = terminal_indices[0]
    if terminal_index != len(events) - 1:
        raise GateError(FailClass.EVENT_AFTER_TERMINAL, "TERMINAL_NOT_LAST", exit_code=ExitCode.PROTOCOL)
    stages = [event.get("stage") for event in events]
    if Stage.DLP_DONE.value not in stages or stages.index(Stage.DLP_DONE.value) > terminal_index:
        raise GateError(FailClass.FINAL_BEFORE_DLP, "DLP_STAGE_MISSING", exit_code=ExitCode.PROTOCOL)
    expected_digest = canonical_sha256(events)
    if verdict.get("event_digest_sha256") != expected_digest:
        raise GateError(FailClass.FINAL_GATE_STALE, "TERMINAL_EVENT_DIGEST", exit_code=ExitCode.PROTOCOL)
    status = verdict.get("status")
    gate = verdict.get("final_gate")
    dlp = next(event for event in events if event.get("stage") == Stage.DLP_DONE.value)
    if (status == "PASS") != (gate == "ALLOW") or (status == "PASS" and dlp.get("outcome") != "PASS"):
        raise GateError(FailClass.TERMINAL_STATUS_MISMATCH, "TERMINAL_BINDING", exit_code=ExitCode.PROTOCOL)
