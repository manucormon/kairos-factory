"""
tests/test_cycling_pipeline.py — CyclingPipeline integration scenarios.

9 scenarios required by the reviewer:
  1. ATTACK intent fires when power > 105% FTP on flat ground
  2. RECOVER intent fires when fatigue >= 0.9
  3. MAINTAIN intent fires at moderate power
  4. EVENT_PASSED when event already occurred
  5. MockTransport receives complete plan signal on delivery
  6. delivery_channels ⊆ active_channels
  7. Touch preserved in active_channels when plan rejected
  8. plan horizon == steps × step_interval_s
  9. all 5 parent signals present in plan lineage
"""

import time
import uuid
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from contracts.kairos_signal import (
    DeliveryReason,
    GovernanceDecision,
    GovernanceReason,
    IntentLabel,
    KairosSignal,
    PayloadType,
    PlanPayload,
    Provenance,
)
from pipelines.cycling import CyclingPipeline


# ---------------------------------------------------------------------------
# MockTransport
# ---------------------------------------------------------------------------

class MockTransport:
    def __init__(self):
        self.calls: List[Tuple[GovernanceDecision, KairosSignal]] = []

    def deliver(
        self,
        decision: GovernanceDecision,
        plan: KairosSignal,
    ) -> None:
        self.calls.append((decision, plan))

    @property
    def last(self) -> Tuple[GovernanceDecision, KairosSignal]:
        assert self.calls, "MockTransport received no calls"
        return self.calls[-1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.monotonic()


def _run(
    *,
    power_w: float = 200.0,
    ftp_w: float = 208.0,
    gradient_pct: float = 0.0,
    fatigue: float = 0.0,
    active_channels: tuple = ("Sound", "Vision"),
    compatible_channels: frozenset = frozenset({"Sound"}),
    event_offset_s: float = 60.0,
    plan_horizon_s: float = 10.0,
    step_interval_s: float = 1.0,
    transport=None,
) -> Tuple[GovernanceDecision, KairosSignal, MockTransport]:
    t = MockTransport() if transport is None else transport
    now = _now()
    pipeline = CyclingPipeline(transport=t)
    dec, plan = pipeline.run(
        power_w=power_w,
        ftp_w=ftp_w,
        gradient_pct=gradient_pct,
        fatigue=fatigue,
        observed_at_s=now - 0.01,
        event_at_s=now + event_offset_s,
        active_channels=active_channels,
        compatible_channels=compatible_channels,
        plan_horizon_s=plan_horizon_s,
        step_interval_s=step_interval_s,
    )
    return dec, plan, t


# ---------------------------------------------------------------------------
# Scenario 1 — ATTACK intent
# ---------------------------------------------------------------------------

class TestAttackIntent:
    def test_attack_fires_above_105_ftp_flat(self):
        """power > 105% FTP, flat gradient, low fatigue → ATTACK intent → high target"""
        # Use short event_offset so plan covers the event (avoid INSUFFICIENT_COVERAGE)
        dec, plan, t = _run(
            power_w=220.0, ftp_w=208.0, gradient_pct=0.0, fatigue=0.1,
            event_offset_s=8.0, plan_horizon_s=10.0, step_interval_s=1.0,
        )
        assert isinstance(plan.payload, PlanPayload)
        # ATTACK targets should be above MAINTAIN (85% FTP = 176.8W)
        assert plan.payload.targets_w[0] > 208.0 * 0.85

    def test_attack_suppressed_at_high_fatigue(self):
        """fatigue >= 0.9 → RECOVER even when power is above FTP"""
        dec, plan, t = _run(power_w=230.0, ftp_w=208.0, gradient_pct=0.0, fatigue=0.95)
        # RECOVER target is 55% FTP = 114.4W
        assert plan.payload.targets_w[0] < 208.0 * 0.7


# ---------------------------------------------------------------------------
# Scenario 2 — RECOVER intent
# ---------------------------------------------------------------------------

class TestRecoverIntent:
    def test_recover_at_high_fatigue(self):
        dec, plan, t = _run(power_w=200.0, ftp_w=208.0, fatigue=0.95)
        target = plan.payload.targets_w[0]
        assert target < 208.0 * 0.7, f"RECOVER target {target}W should be below 70% FTP"

    def test_recover_at_low_power(self):
        dec, plan, t = _run(power_w=100.0, ftp_w=208.0, fatigue=0.0)
        # 100W < 60% of 208W=124.8W → RECOVER
        target = plan.payload.targets_w[0]
        assert target < 208.0 * 0.7


# ---------------------------------------------------------------------------
# Scenario 3 — MAINTAIN intent
# ---------------------------------------------------------------------------

class TestMaintainIntent:
    def test_maintain_at_moderate_power(self):
        dec, plan, t = _run(power_w=170.0, ftp_w=208.0, fatigue=0.3)
        # MAINTAIN → 85% FTP = 176.8W; gradient=0 so no penalty
        target = plan.payload.targets_w[0]
        assert abs(target - 208.0 * 0.85) < 1.0


# ---------------------------------------------------------------------------
# Scenario 4 — EVENT_PASSED
# ---------------------------------------------------------------------------

class TestEventPassed:
    def test_event_already_occurred(self):
        now = _now()
        transport = MockTransport()
        pipeline = CyclingPipeline(transport=transport)
        dec, plan = pipeline.run(
            power_w=200.0,
            ftp_w=208.0,
            gradient_pct=0.0,
            fatigue=0.0,
            observed_at_s=now - 1.0,
            event_at_s=now - 0.5,   # event already passed
            active_channels=("Sound",),
            compatible_channels=frozenset({"Sound"}),
        )
        assert dec.validity_reason == GovernanceReason.EVENT_PASSED
        assert not dec.temporally_eligible
        assert not dec.signal_admitted
        assert dec.delivery_reason == DeliveryReason.TEMPORALLY_INELIGIBLE

    def test_event_passed_before_stale_in_priority(self):
        """Even if signal is expired, EVENT_PASSED must be the reason."""
        now = _now()
        transport = MockTransport()
        pipeline = CyclingPipeline(transport=transport)
        # Force a signal with very short validity by patching event far in past
        dec, plan = pipeline.run(
            power_w=200.0,
            ftp_w=208.0,
            gradient_pct=0.0,
            fatigue=0.0,
            observed_at_s=now - 0.01,
            event_at_s=now - 100.0,  # long in the past
            active_channels=("Sound",),
            compatible_channels=frozenset({"Sound"}),
            plan_horizon_s=0.001,   # valid_until will be now+0.001, but event already gone
        )
        assert dec.validity_reason == GovernanceReason.EVENT_PASSED


# ---------------------------------------------------------------------------
# Scenario 5 — MockTransport receives complete plan signal
# ---------------------------------------------------------------------------

class TestMockTransportDelivery:
    def test_happy_path_full_delivery(self):
        """
        Happy path: event within horizon, compatible channel open, plan admitted.
        Verifies end-to-end delivery — transport receives plan, decision is DELIVERED,
        delivery_channels non-empty, delivery_channels ⊆ active_channels.
        """
        dec, plan, t = _run(
            power_w=170.0,
            ftp_w=208.0,
            gradient_pct=0.0,
            fatigue=0.2,
            active_channels=("Sound", "Vision"),
            compatible_channels=frozenset({"Sound"}),
            event_offset_s=5.0,     # event within 10s horizon — valid
            plan_horizon_s=10.0,
            step_interval_s=1.0,
        )
        # Transport received exactly one call
        assert len(t.calls) == 1
        recv_dec, recv_plan = t.last
        # Plan object passed through unchanged
        assert recv_plan is plan
        assert isinstance(recv_plan.payload, PlanPayload)
        # Admission
        assert recv_dec.signal_admitted, (
            f"Expected DELIVERED but got: {recv_dec.delivery_reason.value} "
            f"(validity: {recv_dec.validity_reason.value})"
        )
        assert recv_dec.delivery_reason == DeliveryReason.DELIVERED
        assert recv_dec.temporally_eligible
        assert recv_dec.validity_reason == GovernanceReason.VALID
        # Channels
        assert len(recv_dec.delivery_channels) > 0
        assert set(recv_dec.delivery_channels).issubset(set(recv_dec.active_channels))
        # Plan payload integrity
        assert recv_plan.payload.observe_only is True
        horizon = recv_plan.valid_until_s - recv_plan.valid_from_s
        expected = recv_plan.payload.steps * recv_plan.payload.step_interval_s
        assert abs(horizon - expected) < 1e-6

    def test_transport_receives_plan_on_delivery(self):
        dec, plan, t = _run(
            power_w=200.0,
            ftp_w=208.0,
            active_channels=("Sound", "Vision"),
            compatible_channels=frozenset({"Sound"}),
            event_offset_s=5.0,   # within horizon
            plan_horizon_s=10.0,
        )
        assert len(t.calls) == 1
        recv_dec, recv_plan = t.last
        assert recv_plan is plan
        assert isinstance(recv_plan.payload, PlanPayload)

    def test_transport_called_even_when_rejected(self):
        dec, plan, t = _run(
            event_offset_s=-10.0,  # event in the past → rejected
        )
        assert len(t.calls) == 1
        recv_dec, _ = t.last
        assert not recv_dec.signal_admitted


# ---------------------------------------------------------------------------
# Scenario 6 — delivery_channels ⊆ active_channels
# ---------------------------------------------------------------------------

class TestChannelSubset:
    def test_delivery_subset_of_active(self):
        dec, plan, t = _run(
            active_channels=("Sound", "Vision", "Touch"),
            compatible_channels=frozenset({"Sound", "Voice", "Vision"}),
            event_offset_s=60.0,
        )
        assert set(dec.delivery_channels).issubset(set(dec.active_channels))

    def test_no_compatible_channel_not_admitted(self):
        dec, plan, t = _run(
            active_channels=("Vision",),
            compatible_channels=frozenset({"Sound"}),   # Sound not active
            event_offset_s=60.0,
        )
        assert not dec.signal_admitted
        assert dec.delivery_channels == ()


# ---------------------------------------------------------------------------
# Scenario 7 — Touch preserved when plan rejected
# ---------------------------------------------------------------------------

class TestTouchPreservedOnRejection:
    def test_touch_in_active_when_plan_stale(self):
        """A rejected/stale plan must not remove Touch from active_channels."""
        now = _now()
        transport = MockTransport()
        pipeline = CyclingPipeline(transport=transport)
        dec, plan = pipeline.run(
            power_w=200.0,
            ftp_w=208.0,
            gradient_pct=0.0,
            fatigue=0.0,
            observed_at_s=now - 0.01,
            event_at_s=now - 5.0,   # event passed → plan rejected
            active_channels=("Touch", "Sound"),
            compatible_channels=frozenset({"Sound"}),
        )
        assert not dec.signal_admitted
        assert "Touch" in dec.active_channels


# ---------------------------------------------------------------------------
# Scenario 8 — plan horizon == steps × step_interval_s
# ---------------------------------------------------------------------------

class TestPlanHorizon:
    def test_horizon_matches_steps_times_interval(self):
        dec, plan, t = _run(plan_horizon_s=10.0, step_interval_s=2.0)
        p = plan.payload
        expected_horizon = p.steps * p.step_interval_s
        actual_horizon = plan.valid_until_s - plan.valid_from_s
        assert abs(actual_horizon - expected_horizon) < 1e-6, (
            f"Horizon mismatch: {actual_horizon:.6f} vs {expected_horizon:.6f}"
        )

    @pytest.mark.parametrize("horizon,interval", [
        (5.0, 1.0),
        (30.0, 5.0),
        (60.0, 10.0),
    ])
    def test_horizon_parametric(self, horizon, interval):
        dec, plan, t = _run(plan_horizon_s=horizon, step_interval_s=interval)
        p = plan.payload
        expected = p.steps * p.step_interval_s
        actual = plan.valid_until_s - plan.valid_from_s
        assert abs(actual - expected) < 1e-6


# ---------------------------------------------------------------------------
# Scenario 9 — plan lineage contains all 5 parent signals
# ---------------------------------------------------------------------------

class TestPlanLineage:
    def test_plan_has_five_parents(self):
        dec, plan, t = _run()
        assert len(plan.parent_signal_ids) == 5, (
            f"Expected 5 parents (power, ftp, gradient, fatigue, intent), "
            f"got {len(plan.parent_signal_ids)}"
        )

    def test_all_parent_ids_are_valid_uuids(self):
        import uuid as _uuid
        dec, plan, t = _run()
        for pid in plan.parent_signal_ids:
            try:
                _uuid.UUID(pid, version=4)
            except ValueError:
                pytest.fail(f"Parent ID {pid!r} is not a valid UUID v4")

    def test_no_duplicate_parent_ids(self):
        dec, plan, t = _run()
        ids = plan.parent_signal_ids
        assert len(ids) == len(set(ids)), "Plan parent_signal_ids contains duplicates"
