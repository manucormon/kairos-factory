"""
pipelines/cycling.py — Cycling domain pipeline for the Kairos family.

Wires the 4 brothers for a single cycling moment:
  sensory_architecture_factory  →  4 atomic KairosSignal inputs
  intent_factory                →  KairosSignal[IntentPayload]
  planning_factory              →  KairosSignal[PlanPayload]
  governance                    →  GovernanceDecision

perception_factory is omitted: its KalmanTracker models 2D physical dynamics
(position, velocity, gravity, bounce). Watt-level power tracking is not a
physics-tracking problem; it belongs in the intent layer.

DATA_LABEL: REAL (power_w from GoldenCheetah OpenData, CC BY 4.0);
           PROXY (ftp_w — estimated 95% of best 20-min, ProcessingStage=DERIVED);
           DECLARED (gradient_pct and fatigue — caller-supplied).
"""

from __future__ import annotations

import time
import uuid
from typing import FrozenSet, Optional, Protocol, Tuple

from contracts.kairos_signal import (
    SCHEMA_VERSION,
    DeliveryReason,
    FatiguePayload,
    FtpPayload,
    GovernanceDecision,
    GovernanceReason,
    GradientPayload,
    IntentLabel,
    IntentPayload,
    KairosSignal,
    PayloadType,
    PlanPayload,
    PowerPayload,
    ProcessingStage,
    Provenance,
    build_governance_decision,
    check_temporality,
)

PRODUCER = "kairos/cycling-pipeline"
PRODUCER_VERSION = "1.0"
DOMAIN = "cycling"


# ---------------------------------------------------------------------------
# Transport protocol — enables MockTransport in tests
# ---------------------------------------------------------------------------

class Transport(Protocol):
    def deliver(self, decision: GovernanceDecision, plan: "KairosSignal[PlanPayload]") -> None:
        ...


class LoggingTransport:
    """Default transport: prints delivery summary to stdout."""

    def deliver(
        self,
        decision: GovernanceDecision,
        plan: "KairosSignal[PlanPayload]",
    ) -> None:
        if decision.signal_admitted:
            channels = ", ".join(sorted(decision.delivery_channels))
            print(
                f"[DELIVER] signal={plan.signal_id[:8]}... "
                f"channels={channels} "
                f"reason={decision.delivery_reason.value}"
            )
        else:
            print(
                f"[BLOCKED] signal={plan.signal_id[:8]}... "
                f"reason={decision.delivery_reason.value}"
            )


# ---------------------------------------------------------------------------
# CyclingPipeline
# ---------------------------------------------------------------------------

class CyclingPipeline:
    """
    Execute one Kairos cycle for the cycling domain.

    Inputs:
        power_w       — watts at this moment (REAL, MEASURED)
        ftp_w         — functional threshold power (PROXY, DERIVED — 95% best 20-min)
        gradient_pct  — road gradient in [-20, 20] (DECLARED, MEASURED)
        fatigue       — rider fatigue in [0, 1] (DECLARED, MEASURED) — caller-supplied
        observed_at_s — monotonic timestamp when the sensor fired
        event_at_s    — when the target event (e.g. climb summit) occurs
        active_channels        — channels open system-wide (govern_hybrid result)
        compatible_channels    — channels that can carry this plan type
        session_id    — UUID v4 shared across the current ride session
        transport     — where to send the GovernanceDecision + plan signal
    """

    def __init__(self, transport: Optional[Transport] = None) -> None:
        self._transport = transport or LoggingTransport()

    def run(
        self,
        *,
        power_w: float,
        ftp_w: float,
        gradient_pct: float,
        fatigue: float,
        observed_at_s: float,
        event_at_s: float,
        active_channels: Tuple[str, ...],
        compatible_channels: FrozenSet[str],
        session_id: Optional[str] = None,
        plan_horizon_s: float = 10.0,
        step_interval_s: float = 1.0,
    ) -> Tuple[GovernanceDecision, "KairosSignal[PlanPayload]"]:

        sid = session_id or str(uuid.uuid4())
        produced_at_s = time.monotonic()
        compute_start = produced_at_s

        # --- Brother 01 (sensory): 4 atomic input signals ---
        power_sig = self._make_signal(
            payload=PowerPayload(power_w=power_w),
            payload_type=PayloadType.POWER,
            unit="W",
            provenance=Provenance.REAL,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + plan_horizon_s,
            session_id=sid,
            parents=(),
        )
        ftp_sig = self._make_signal(
            payload=FtpPayload(ftp_w=ftp_w),
            payload_type=PayloadType.FTP,
            unit="W",
            provenance=Provenance.PROXY,
            stage=ProcessingStage.DERIVED,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + plan_horizon_s,
            session_id=sid,
            parents=(),
        )
        gradient_sig = self._make_signal(
            payload=GradientPayload(gradient_pct=gradient_pct),
            payload_type=PayloadType.GRADIENT,
            unit="%",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + plan_horizon_s,
            session_id=sid,
            parents=(),
        )
        fatigue_sig = self._make_signal(
            payload=FatiguePayload(fatigue=fatigue),
            payload_type=PayloadType.FATIGUE,
            unit="",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + plan_horizon_s,
            session_id=sid,
            parents=(),
        )

        # --- Brother 02 (intent): classify intent ---
        intent_label = self._classify_intent(power_w, ftp_w, fatigue, gradient_pct)
        intent_parents = (
            power_sig.signal_id,
            ftp_sig.signal_id,
            gradient_sig.signal_id,
            fatigue_sig.signal_id,
        )
        intent_sig = self._make_signal(
            payload=IntentPayload(
                label=intent_label,
                attack_suppressed=(fatigue >= 0.9),
                calibrated_probability=None,
            ),
            payload_type=PayloadType.INTENT,
            unit="label",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.CLASSIFIED,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + plan_horizon_s,
            session_id=sid,
            parents=intent_parents,
        )

        # --- Brother 03 (planning): build plan ---
        steps = max(1, round(plan_horizon_s / step_interval_s))
        targets = self._build_targets(
            intent_label, power_w, ftp_w, steps, gradient_pct
        )
        plan_parents = (
            power_sig.signal_id,
            ftp_sig.signal_id,
            gradient_sig.signal_id,
            fatigue_sig.signal_id,
            intent_sig.signal_id,
        )
        compute_latency_ms = (time.monotonic() - compute_start) * 1000.0
        plan_valid_from = observed_at_s
        plan_valid_until = observed_at_s + steps * step_interval_s

        plan_sig: KairosSignal[PlanPayload] = KairosSignal(
            schema_version=SCHEMA_VERSION,
            signal_id=str(uuid.uuid4()),
            domain=DOMAIN,
            session_id=sid,
            payload=PlanPayload(
                targets_w=tuple(targets),
                steps=steps,
                step_interval_s=step_interval_s,
                observe_only=True,
            ),
            payload_type=PayloadType.PLAN,
            unit="W",
            provenance=Provenance.DECLARED,
            processing_stage=ProcessingStage.PLANNED,
            producer=PRODUCER,
            producer_version=PRODUCER_VERSION,
            parent_signal_ids=plan_parents,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            compute_latency_ms=compute_latency_ms,
            valid_from_s=plan_valid_from,
            valid_until_s=plan_valid_until,
        )

        # --- Brother 04 (sensory governance): evaluate and deliver ---
        decision = build_governance_decision(
            signal=plan_sig,
            now_s=produced_at_s,
            event_at_s=event_at_s,
            active_channels=active_channels,
            compatible_delivery_channels=compatible_channels,
        )
        self._transport.deliver(decision, plan_sig)
        return decision, plan_sig

    # -----------------------------------------------------------------------

    def _make_signal(
        self,
        *,
        payload,
        payload_type: PayloadType,
        unit: str,
        provenance: Provenance,
        stage: ProcessingStage,
        observed_at_s: float,
        produced_at_s: float,
        valid_from_s: float,
        valid_until_s: float,
        session_id: str,
        parents: Tuple[str, ...],
    ) -> KairosSignal:
        return KairosSignal(
            schema_version=SCHEMA_VERSION,
            signal_id=str(uuid.uuid4()),
            domain=DOMAIN,
            session_id=session_id,
            payload=payload,
            payload_type=payload_type,
            unit=unit,
            provenance=provenance,
            processing_stage=stage,
            producer=PRODUCER,
            producer_version=PRODUCER_VERSION,
            parent_signal_ids=parents,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            compute_latency_ms=0.0,
            valid_from_s=valid_from_s,
            valid_until_s=valid_until_s,
        )

    @staticmethod
    def _classify_intent(
        power_w: float,
        ftp_w: float,
        fatigue: float,
        gradient_pct: float,
    ) -> IntentLabel:
        if ftp_w <= 0:
            return IntentLabel.RECOVER
        ratio = power_w / ftp_w
        if fatigue >= 0.9:
            return IntentLabel.RECOVER
        if ratio > 1.05 and gradient_pct >= 0:
            return IntentLabel.ATTACK
        if ratio < 0.6:
            return IntentLabel.RECOVER
        return IntentLabel.MAINTAIN

    @staticmethod
    def _build_targets(
        label: IntentLabel,
        current_w: float,
        ftp_w: float,
        steps: int,
        gradient_pct: float,
    ) -> List[float]:
        if label == IntentLabel.ATTACK:
            target = min(current_w * 1.05, ftp_w * 1.2)
        elif label == IntentLabel.RECOVER:
            target = ftp_w * 0.55
        else:
            target = ftp_w * 0.85

        gradient_penalty = max(0.0, gradient_pct) * 0.5
        target = max(0.0, target - gradient_penalty)
        return [round(target, 1)] * steps
