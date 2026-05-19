"""card2_routing.py — D-4 Card 2 문서 변환 모델 라우팅.

문서 크기로 tier(S/M/L/XL)를 분류하고, 장치 상태 3중 게이트로 L tier 의
4B 모델 사용 여부를 결정한다. 게이트 1건이라도 실패하면 1.7B fallback 으로
강등하며 fallback 에서는 auto_fill 을 영구 금지한다 (M-62 정합).

외부 API 호출 0 · 학습 변경 0 · 모델 weight 변경 0.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

# ── tier 분류 임계 (문서 바이트 기준) ────────────────────────────────────────
TIER_S_MAX_BYTES = 64 * 1024          # ~64KB 이하 S
TIER_M_MAX_BYTES = 512 * 1024         # ~512KB 이하 M
TIER_L_MAX_BYTES = 4 * 1024 * 1024    # ~4MB 이하 L, 초과 XL(차단)

# ── 모델별 임계 (단일 표준 — 명령서 v1.1 §6) ─────────────────────────────────
THRESHOLDS_1_7B = {"auto_fill": 0.82, "review_low": 0.70, "blank": 0.70}
THRESHOLDS_4B   = {"auto_fill": 0.85, "review_low": 0.72, "blank": 0.72}
# 1.7B L fallback: auto_fill 영구 금지 (confidence 무관), review 0.70~1.00
THRESHOLDS_1_7B_L_FALLBACK = {"auto_fill": None, "review_low": 0.70, "blank": 0.70}

# ── L tier 4B 게이트 ─────────────────────────────────────────────────────────
GATE_MIN_FREE_RAM_GB = 6.0
GATE_MIN_BATTERY_PCT = 30
GATE_OK_THERMAL = {"normal", "nominal", "fair"}


@dataclass(frozen=True)
class DeviceState:
    """장치 상태 스냅샷 — 측정 불가 필드는 보수적 기본값(게이트 실패 방향)."""
    is_m3_max: bool = False
    free_ram_gb: float = 0.0
    battery_percent: int = 0
    thermal_state: str = "unknown"
    measured: bool = False  # 실측 여부 — False면 게이트는 fallback 으로 처리


@dataclass(frozen=True)
class RoutingDecision:
    tier: str
    model: str                              # "butler-1.7b-q4_k_m" | "qwen3-4b-q4_k_m"
    auto_fill_allowed: bool
    threshold_auto_fill: Optional[float]    # fallback 시 None
    threshold_review_low: float
    threshold_blank: float
    reason: str
    gate_failures: tuple = field(default_factory=tuple)


def classify_card2_tier(doc_size_bytes: int) -> str:
    """문서 바이트 수 → tier. XL 은 차단 대상."""
    if doc_size_bytes < 0:
        raise ValueError("doc_size_bytes must be >= 0")
    if doc_size_bytes <= TIER_S_MAX_BYTES:
        return "S"
    if doc_size_bytes <= TIER_M_MAX_BYTES:
        return "M"
    if doc_size_bytes <= TIER_L_MAX_BYTES:
        return "L"
    return "XL"


def measure_device_state(
    *,
    is_m3_max: Optional[bool] = None,
    free_ram_gb: Optional[float] = None,
    battery_percent: Optional[int] = None,
    thermal_state: Optional[str] = None,
) -> DeviceState:
    """장치 상태 측정. 인자가 주어지면 그대로 사용(테스트/주입), 아니면 best-effort
    local 측정 시도. 측정 실패 항목은 보수적 기본값(게이트 실패 방향)으로 둔다.

    외부 네트워크 호출 0 — 로컬 OS 조회만.
    """
    if None not in (is_m3_max, free_ram_gb, battery_percent, thermal_state):
        return DeviceState(
            is_m3_max=bool(is_m3_max),
            free_ram_gb=float(free_ram_gb),
            battery_percent=int(battery_percent),
            thermal_state=str(thermal_state),
            measured=True,
        )
    # best-effort local 측정 (psutil 미설치 등 실패 시 보수적 기본값)
    measured = False
    _ram = free_ram_gb if free_ram_gb is not None else 0.0
    _bat = battery_percent if battery_percent is not None else 0
    _m3 = bool(is_m3_max) if is_m3_max is not None else False
    _thermal = thermal_state if thermal_state is not None else "unknown"
    try:
        import psutil  # type: ignore
        if free_ram_gb is None:
            _ram = psutil.virtual_memory().available / (1024 ** 3)
        if battery_percent is None:
            bat = psutil.sensors_battery()
            _bat = int(bat.percent) if bat is not None else 100  # AC 전원 가정
        measured = True
    except Exception:
        measured = False
    return DeviceState(
        is_m3_max=_m3, free_ram_gb=float(_ram),
        battery_percent=int(_bat), thermal_state=str(_thermal),
        measured=measured,
    )


def _l_gate_failures(state: DeviceState) -> tuple:
    """L tier 4B 게이트 실패 항목 목록 반환 (빈 tuple = 전부 통과)."""
    fails = []
    if not state.is_m3_max:
        fails.append("not_m3_max")
    if state.free_ram_gb < GATE_MIN_FREE_RAM_GB:
        fails.append(f"free_ram<{GATE_MIN_FREE_RAM_GB}")
    if state.battery_percent < GATE_MIN_BATTERY_PCT:
        fails.append(f"battery<{GATE_MIN_BATTERY_PCT}")
    if state.thermal_state not in GATE_OK_THERMAL:
        fails.append(f"thermal={state.thermal_state}")
    if not state.measured:
        fails.append("device_state_not_measured")
    return tuple(fails)


def choose_card2_mapping_model(tier: str, device_state: DeviceState) -> RoutingDecision:
    """tier + 장치 상태 → RoutingDecision.

    S/M → 1.7B (auto_fill 허용). L → 게이트 전수 통과 시 4B(auto_fill 허용),
    1건이라도 실패 시 1.7B fallback(auto_fill 영구 금지). XL → 차단.
    """
    if tier == "XL":
        return RoutingDecision(
            tier="XL", model="blocked", auto_fill_allowed=False,
            threshold_auto_fill=None, threshold_review_low=1.0,
            threshold_blank=1.0, reason="XL tier — 처리 차단 (크기 초과)",
        )
    if tier in ("S", "M"):
        return RoutingDecision(
            tier=tier, model="butler-1.7b-q4_k_m", auto_fill_allowed=True,
            threshold_auto_fill=THRESHOLDS_1_7B["auto_fill"],
            threshold_review_low=THRESHOLDS_1_7B["review_low"],
            threshold_blank=THRESHOLDS_1_7B["blank"],
            reason=f"{tier} tier — 1.7B 표준 라우팅",
        )
    if tier == "L":
        fails = _l_gate_failures(device_state)
        if not fails:
            return RoutingDecision(
                tier="L", model="qwen3-4b-q4_k_m", auto_fill_allowed=True,
                threshold_auto_fill=THRESHOLDS_4B["auto_fill"],
                threshold_review_low=THRESHOLDS_4B["review_low"],
                threshold_blank=THRESHOLDS_4B["blank"],
                reason="L tier — 4B 게이트 3중 전수 통과",
            )
        return RoutingDecision(
            tier="L", model="butler-1.7b-q4_k_m", auto_fill_allowed=False,
            threshold_auto_fill=THRESHOLDS_1_7B_L_FALLBACK["auto_fill"],
            threshold_review_low=THRESHOLDS_1_7B_L_FALLBACK["review_low"],
            threshold_blank=THRESHOLDS_1_7B_L_FALLBACK["blank"],
            reason="L tier — 게이트 실패 → 1.7B fallback (auto_fill 영구 금지)",
            gate_failures=fails,
        )
    raise ValueError(f"unknown tier: {tier}")


def audit_card2_routing_decision(
    decision: RoutingDecision, doc_size_bytes: int, device_state: DeviceState,
) -> dict:
    """라우팅 결정 감사 레코드 — raw 문서 내용 미포함, 메타만."""
    return {
        "evidence_kind": "real_run",
        "measured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tier": decision.tier,
        "doc_size_bytes": int(doc_size_bytes),
        "model": decision.model,
        "auto_fill_allowed": decision.auto_fill_allowed,
        "threshold_auto_fill": decision.threshold_auto_fill,
        "threshold_review_low": decision.threshold_review_low,
        "threshold_blank": decision.threshold_blank,
        "gate_failures": list(decision.gate_failures),
        "device_state": {
            "is_m3_max": device_state.is_m3_max,
            "free_ram_gb": round(device_state.free_ram_gb, 2),
            "battery_percent": device_state.battery_percent,
            "thermal_state": device_state.thermal_state,
            "measured": device_state.measured,
        },
        "reason": decision.reason,
    }
