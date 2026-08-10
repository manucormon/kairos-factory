"""
tests/test_cycling_pipeline.py — CyclingPipeline integration scenarios.

Integration scenarios:
  1. ATTACK intent fires when power > 105% FTP on flat ground
  2. RECOVER intent fires when fatigue >= 0.9
  3. MAINTAIN intent fires at moderate power
  4. EVENT_PASSED when event already occurred
  5. MockTransport receives complete plan signal on delivery
  6. delivery_channels ⊆ active_channels
  7. Touch preserved in active_channels when plan rejected
  8. plan horizon == steps × step_interval_s
  9. all 5 parent signals present in plan lineage
 10. boundary behavior and target arrays match the real brother implementations
 11. injected brother ports are actually used
"""

import time
from types import SimpleNamespace
from typing import List, Tuple

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
from pipelines.cycling import (
    CyclingPipeline,
    _default_intent_classifier,
    _default_planner_factory,
)


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


class RecordingPlannerFactory:
    """Wrap the real planning brother and record every orchestration call."""

    def __init__(self):
        self.calls = []

    def __call__(self, dt: float):
        delegate = _default_planner_factory(dt)
        owner = self

        class RecordingPlanner:
            def plan(self, **kwargs):
                owner.calls.append((dt, dict(kwargs)))
                return delegate.plan(**kwargs)

        return RecordingPlanner()


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
    intent_classifier=None,
    planner_factory=None,
) -> Tuple[GovernanceDecision, KairosSignal, MockTransport]:
    t = MockTransport() if transport is None else transport
    now = _now()
    pipeline = CyclingPipeline(
        transport=t,
        intent_classifier=intent_classifier,
        planner_factory=planner_factory,
    )
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
        # The real planner ramps from current power and then holds above FTP.
        assert plan.payload.targets_w[-1] > 208.0 * 1.05

    def test_attack_suppressed_at_high_fatigue(self):
        """fatigue >= 0.9 → RECOVER even when power is above FTP"""
        dec, plan, t = _run(power_w=230.0, ftp_w=208.0, gradient_pct=0.0, fatigue=0.95)
        # The real planner decays from current power to 50% FTP.
        assert plan.payload.targets_w[-1] == pytest.approx(208.0 * 0.50)


# ---------------------------------------------------------------------------
# Scenario 2 — RECOVER intent
# ---------------------------------------------------------------------------

class TestRecoverIntent:
    def test_recover_at_high_fatigue(self):
        dec, plan, t = _run(power_w=200.0, ftp_w=208.0, fatigue=0.95)
        target = plan.payload.targets_w[-1]
        assert target < 208.0 * 0.7, f"RECOVER target {target}W should be below 70% FTP"

    def test_recover_at_low_power(self):
        dec, plan, t = _run(power_w=100.0, ftp_w=208.0, fatigue=0.0)
        # 100W < 55% of 208W=114.4W → RECOVER
        target = plan.payload.targets_w[-1]
        assert target < 208.0 * 0.7


# ---------------------------------------------------------------------------
# Scenario 3 — MAINTAIN intent
# ---------------------------------------------------------------------------

class TestMaintainIntent:
    def test_maintain_at_moderate_power(self):
        dec, plan, t = _run(power_w=170.0, ftp_w=208.0, fatigue=0.3)
        # Real planner holds the current ratio on flat ground.
        target = plan.payload.targets_w[0]
        assert target == pytest.approx(170.0)


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

    def test_non_divisible_horizon_rounds_up_without_undercoverage(self):
        _, plan, _ = _run(plan_horizon_s=10.0, step_interval_s=3.0)
        assert plan.payload.steps == 4
        assert plan.valid_until_s - plan.valid_from_s == pytest.approx(12.0)


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


# ---------------------------------------------------------------------------
# Scenario 10 — parity with the checked-out brothers
# ---------------------------------------------------------------------------

class TestBrotherParity:
    @pytest.mark.parametrize(
        "power_ratio,gradient_pct,fatigue,expected_label",
        [
            (1.05, 0.0, 0.10, "MAINTAIN"),      # ATTACK is strictly > 1.05
            (1.0501, 15.0, 0.10, "ATTACK"),     # gradient ceiling is strictly > 15
            (1.0501, 15.0001, 0.10, "MAINTAIN"),
            (1.0501, 0.0, 0.8499, "ATTACK"),
            (1.0501, 0.0, 0.85, "MAINTAIN"),
            (1.0501, 0.0, 0.90, "RECOVER"),
            (0.55, 0.0, 0.10, "MAINTAIN"),      # RECOVER is strictly < 0.55
            (0.5499, 0.0, 0.10, "RECOVER"),
        ],
    )
    def test_boundary_label_and_targets_match_brothers(
        self, power_ratio, gradient_pct, fatigue, expected_label
    ):
        ftp_w = 200.0
        power_w = ftp_w * power_ratio
        classifier = _default_intent_classifier()
        expected_state = classifier.classify(
            power_w=power_w,
            ftp_w=ftp_w,
            gradient_pct=gradient_pct,
            fatigue=fatigue,
        )
        assert expected_state.label == expected_label

        recording_factory = RecordingPlannerFactory()
        _, plan, _ = _run(
            power_w=power_w,
            ftp_w=ftp_w,
            gradient_pct=gradient_pct,
            fatigue=fatigue,
            event_offset_s=5.0,
            planner_factory=recording_factory,
        )

        assert len(recording_factory.calls) == 1
        dt, kwargs = recording_factory.calls[0]
        assert kwargs["intent"] == expected_state.label
        expected_plan = _default_planner_factory(dt).plan(**kwargs)
        assert plan.payload.targets_w == tuple(expected_plan.targets_w)
        assert plan.payload.observe_only is expected_plan.observe_only is True
        assert plan.valid_until_s - plan.valid_from_s == pytest.approx(
            expected_plan.dt_ahead
        )


# ---------------------------------------------------------------------------
# Scenario 11 — dependency injection and timing validation
# ---------------------------------------------------------------------------

class TestBrotherPorts:
    def test_injected_classifier_and_planner_are_used(self):
        classifier = SimpleNamespace()
        classifier.classify = lambda **kwargs: SimpleNamespace(
            label="RECOVER", attack_suppressed=False
        )

        class FixedPlanner:
            def plan(self, **kwargs):
                assert kwargs["intent"] == "RECOVER"
                return SimpleNamespace(
                    targets_w=[123.0] * kwargs["steps"],
                    dt_ahead=kwargs["steps"] * 1.0,
                    observe_only=True,
                )

        _, plan, _ = _run(
            intent_classifier=classifier,
            planner_factory=lambda dt: FixedPlanner(),
        )
        assert plan.payload.targets_w == (123.0,) * plan.payload.steps

    @pytest.mark.parametrize(
        "horizon,interval",
        [(0.0, 1.0), (-1.0, 1.0), (10.0, 0.0), (10.0, -1.0)],
    )
    def test_invalid_plan_timing_is_rejected(self, horizon, interval):
        with pytest.raises(ValueError, match="positive and finite"):
            _run(plan_horizon_s=horizon, step_interval_s=interval)
