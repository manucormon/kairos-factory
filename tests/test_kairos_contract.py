"""
tests/test_kairos_contract.py — KairosSignal contract invariants.

Covers all cases the reviewer required:
  - EVENT_PASSED fires before NOT_YET_VALID and STALE
  - temporally_eligible == (validity_reason == VALID)
  - signal_admitted == (delivery_reason == DELIVERED)
  - delivery_channels ⊆ active_channels
  - Touch active when plan rejected (independent reflex)
  - payload type / discriminator mismatch raises
  - plan horizon == steps × step_interval_s
  - gradient range check
  - full round-trip via to_dict / from_dict
"""

import math
import uuid
import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sid() -> str:
    return str(uuid.uuid4())


def _power_signal(
    *,
    power_w: float = 200.0,
    observed_at_s: float = 100.0,
    produced_at_s: float = 100.1,
    valid_from_s: float = 100.0,
    valid_until_s: float = 110.0,
    session_id=None,
    parents: tuple = (),
) -> KairosSignal:
    return KairosSignal(
        schema_version=SCHEMA_VERSION,
        signal_id=_sid(),
        domain="cycling",
        session_id=session_id or _sid(),
        payload=PowerPayload(power_w=power_w),
        payload_type=PayloadType.POWER,
        unit="W",
        provenance=Provenance.REAL,
        processing_stage=ProcessingStage.MEASURED,
        producer="test",
        producer_version="0",
        parent_signal_ids=parents,
        observed_at_s=observed_at_s,
        produced_at_s=produced_at_s,
        compute_latency_ms=0.5,
        valid_from_s=valid_from_s,
        valid_until_s=valid_until_s,
    )


def _plan_signal(
    *,
    steps: int = 5,
    step_interval_s: float = 2.0,
    observed_at_s: float = 100.0,
    produced_at_s: float = 100.1,
    valid_from_s: float = 100.0,
    valid_until_s=None,
    parents: tuple = (),
    session_id=None,
) -> KairosSignal:
    if valid_until_s is None:
        valid_until_s = valid_from_s + steps * step_interval_s
    return KairosSignal(
        schema_version=SCHEMA_VERSION,
        signal_id=_sid(),
        domain="cycling",
        session_id=session_id or _sid(),
        payload=PlanPayload(
            targets_w=tuple([200.0] * steps),
            steps=steps,
            step_interval_s=step_interval_s,
            observe_only=True,
        ),
        payload_type=PayloadType.PLAN,
        unit="W",
        provenance=Provenance.DECLARED,
        processing_stage=ProcessingStage.PLANNED,
        producer="test",
        producer_version="0",
        parent_signal_ids=parents,
        observed_at_s=observed_at_s,
        produced_at_s=produced_at_s,
        compute_latency_ms=1.0,
        valid_from_s=valid_from_s,
        valid_until_s=valid_until_s,
    )


# ---------------------------------------------------------------------------
# Temporality — GovernanceReason ordering
# ---------------------------------------------------------------------------

class TestCheckTemporality:
    def test_future_timestamp_observed(self):
        sig = _power_signal(observed_at_s=200.0, produced_at_s=200.1,
                            valid_from_s=200.0, valid_until_s=210.0)
        # now < observed_at_s → FUTURE_TIMESTAMP takes priority
        assert check_temporality(sig, now_s=100.0, event_at_s=300.0) == GovernanceReason.FUTURE_TIMESTAMP

    def test_future_timestamp_produced(self):
        sig = _power_signal(observed_at_s=100.0, produced_at_s=200.0,
                            valid_from_s=100.0, valid_until_s=210.0)
        assert check_temporality(sig, now_s=150.0, event_at_s=300.0) == GovernanceReason.FUTURE_TIMESTAMP

    def test_event_passed_before_not_yet_valid(self):
        # event already happened; signal not yet valid — EVENT_PASSED wins
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=200.0, valid_until_s=210.0)
        assert check_temporality(sig, now_s=100.0, event_at_s=90.0) == GovernanceReason.EVENT_PASSED

    def test_event_passed_before_stale(self):
        # signal expired AND event passed — EVENT_PASSED wins
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=50.0, valid_until_s=60.0)
        assert check_temporality(sig, now_s=100.0, event_at_s=80.0) == GovernanceReason.EVENT_PASSED

    def test_not_yet_valid(self):
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=200.0, valid_until_s=210.0)
        # event is in the future, now < valid_from
        assert check_temporality(sig, now_s=100.0, event_at_s=300.0) == GovernanceReason.NOT_YET_VALID

    def test_stale(self):
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=50.0, valid_until_s=60.0)
        # now >= valid_until_s; event still in future
        assert check_temporality(sig, now_s=100.0, event_at_s=300.0) == GovernanceReason.STALE

    def test_insufficient_coverage(self):
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=50.0, valid_until_s=110.0)
        # valid but expires before event
        assert check_temporality(sig, now_s=100.0, event_at_s=200.0) == GovernanceReason.INSUFFICIENT_COVERAGE

    def test_valid(self):
        sig = _power_signal(observed_at_s=50.0, produced_at_s=50.1,
                            valid_from_s=50.0, valid_until_s=300.0)
        assert check_temporality(sig, now_s=100.0, event_at_s=200.0) == GovernanceReason.VALID


# ---------------------------------------------------------------------------
# GovernanceDecision invariants
# ---------------------------------------------------------------------------

class TestGovernanceDecisionInvariants:
    def test_temporally_eligible_equals_valid(self):
        sig = _plan_signal()
        dec = build_governance_decision(
            signal=sig,
            now_s=100.1,
            event_at_s=200.0,
            active_channels=("Sound", "Vision"),
            compatible_delivery_channels=frozenset({"Sound"}),
        )
        assert dec.temporally_eligible == (dec.validity_reason == GovernanceReason.VALID)

    def test_signal_admitted_equals_delivered(self):
        sig = _plan_signal()
        dec = build_governance_decision(
            signal=sig,
            now_s=100.1,
            event_at_s=200.0,
            active_channels=("Sound", "Vision"),
            compatible_delivery_channels=frozenset({"Sound"}),
        )
        assert dec.signal_admitted == (dec.delivery_reason == DeliveryReason.DELIVERED)

    def test_delivery_channels_subset_of_active(self):
        sig = _plan_signal()
        dec = build_governance_decision(
            signal=sig,
            now_s=100.1,
            event_at_s=200.0,
            active_channels=("Sound", "Vision", "Touch"),
            compatible_delivery_channels=frozenset({"Sound", "Voice"}),
        )
        assert set(dec.delivery_channels).issubset(set(dec.active_channels))

    def test_delivery_channels_empty_when_not_admitted(self):
        # plan is STALE → not admitted → delivery_channels must be empty
        sig = _plan_signal(
            observed_at_s=50.0, produced_at_s=50.1,
            valid_from_s=50.0, valid_until_s=60.0,
        )
        dec = build_governance_decision(
            signal=sig,
            now_s=100.0,
            event_at_s=300.0,
            active_channels=("Sound",),
            compatible_delivery_channels=frozenset({"Sound"}),
        )
        assert not dec.signal_admitted
        assert dec.delivery_channels == ()

    def test_touch_active_when_plan_rejected(self):
        """A stale plan must not silence Touch — active_channels preserved."""
        sig = _plan_signal(
            observed_at_s=50.0, produced_at_s=50.1,
            valid_from_s=50.0, valid_until_s=60.0,
        )
        dec = build_governance_decision(
            signal=sig,
            now_s=100.0,
            event_at_s=300.0,
            active_channels=("Touch", "Sound"),
            compatible_delivery_channels=frozenset({"Sound"}),
        )
        assert "Touch" in dec.active_channels
        assert not dec.signal_admitted

    def test_evaluated_signal_id_matches(self):
        sig = _plan_signal()
        dec = build_governance_decision(
            signal=sig,
            now_s=100.1,
            event_at_s=200.0,
            active_channels=("Sound",),
            compatible_delivery_channels=frozenset({"Sound"}),
        )
        assert dec.evaluated_signal_id == sig.signal_id

    def test_direct_construction_delivery_channels_not_subset_raises(self):
        with pytest.raises(ValueError, match="subset"):
            GovernanceDecision(
                temporally_eligible=True,
                validity_reason=GovernanceReason.VALID,
                signal_admitted=True,
                delivery_reason=DeliveryReason.DELIVERED,
                active_channels=("Sound",),
                delivery_channels=("Voice",),   # not in active
                evaluated_signal_id=_sid(),
                evaluated_at_s=100.0,
                event_at_s=200.0,
            )

    def test_direct_construction_admitted_mismatch_raises(self):
        with pytest.raises(ValueError, match="signal_admitted"):
            GovernanceDecision(
                temporally_eligible=True,
                validity_reason=GovernanceReason.VALID,
                signal_admitted=False,              # wrong
                delivery_reason=DeliveryReason.DELIVERED,
                active_channels=("Sound",),
                delivery_channels=(),
                evaluated_signal_id=_sid(),
                evaluated_at_s=100.0,
                event_at_s=200.0,
            )


# ---------------------------------------------------------------------------
# KairosSignal validation
# ---------------------------------------------------------------------------

class TestKairosSignalValidation:
    def test_payload_type_mismatch_raises(self):
        with pytest.raises(ValueError, match="payload_type"):
            KairosSignal(
                schema_version=SCHEMA_VERSION,
                signal_id=_sid(),
                domain="cycling",
                session_id=_sid(),
                payload=PowerPayload(power_w=200.0),
                payload_type=PayloadType.FTP,    # wrong
                unit="W",
                provenance=Provenance.REAL,
                processing_stage=ProcessingStage.MEASURED,
                producer="test",
                producer_version="0",
                parent_signal_ids=(),
                observed_at_s=100.0,
                produced_at_s=100.1,
                compute_latency_ms=0.0,
                valid_from_s=100.0,
                valid_until_s=110.0,
            )

    def test_self_reference_in_parents_raises(self):
        sid = _sid()
        with pytest.raises(ValueError, match="signal_id must not appear"):
            KairosSignal(
                schema_version=SCHEMA_VERSION,
                signal_id=sid,
                domain="cycling",
                session_id=_sid(),
                payload=PowerPayload(power_w=200.0),
                payload_type=PayloadType.POWER,
                unit="W",
                provenance=Provenance.REAL,
                processing_stage=ProcessingStage.MEASURED,
                producer="test",
                producer_version="0",
                parent_signal_ids=(sid,),           # self-ref
                observed_at_s=100.0,
                produced_at_s=100.1,
                compute_latency_ms=0.0,
                valid_from_s=100.0,
                valid_until_s=110.0,
            )

    def test_plan_horizon_mismatch_raises(self):
        with pytest.raises(ValueError, match="horizon"):
            KairosSignal(
                schema_version=SCHEMA_VERSION,
                signal_id=_sid(),
                domain="cycling",
                session_id=_sid(),
                payload=PlanPayload(
                    targets_w=(200.0,) * 5,
                    steps=5,
                    step_interval_s=2.0,
                    observe_only=True,
                ),
                payload_type=PayloadType.PLAN,
                unit="W",
                provenance=Provenance.DECLARED,
                processing_stage=ProcessingStage.PLANNED,
                producer="test",
                producer_version="0",
                parent_signal_ids=(),
                observed_at_s=100.0,
                produced_at_s=100.1,
                compute_latency_ms=0.0,
                valid_from_s=100.0,
                valid_until_s=115.0,    # should be 110.0 = 5×2
            )

    def test_gradient_out_of_range_raises(self):
        with pytest.raises(ValueError, match="gradient"):
            GradientPayload(gradient_pct=25.0)   # > 20

    def test_gradient_lower_bound(self):
        with pytest.raises(ValueError):
            GradientPayload(gradient_pct=-21.0)

    def test_gradient_in_range_ok(self):
        g = GradientPayload(gradient_pct=-20.0)
        assert g.gradient_pct == -20.0
        g2 = GradientPayload(gradient_pct=20.0)
        assert g2.gradient_pct == 20.0

    def test_observe_only_false_raises(self):
        with pytest.raises(ValueError, match="observe_only"):
            PlanPayload(
                targets_w=(200.0,),
                steps=1,
                step_interval_s=1.0,
                observe_only=False,
            )

    def test_negative_power_raises(self):
        with pytest.raises(ValueError):
            PowerPayload(power_w=-1.0)

    def test_zero_ftp_raises(self):
        with pytest.raises(ValueError):
            FtpPayload(ftp_w=0.0)

    def test_fatigue_out_of_range_raises(self):
        with pytest.raises(ValueError):
            FatiguePayload(fatigue=1.1)

    def test_duplicate_parents_raises(self):
        pid = _sid()
        with pytest.raises(ValueError, match="duplicate"):
            _power_signal(parents=(pid, pid))


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_power_signal_round_trip(self):
        sig = _power_signal(power_w=250.5)
        restored = KairosSignal.from_dict(sig.to_dict())
        assert restored.signal_id == sig.signal_id
        assert isinstance(restored.payload, PowerPayload)
        assert restored.payload.power_w == 250.5
        assert restored.provenance == Provenance.REAL

    def test_intent_signal_round_trip(self):
        sig = KairosSignal(
            schema_version=SCHEMA_VERSION,
            signal_id=_sid(),
            domain="cycling",
            session_id=_sid(),
            payload=IntentPayload(
                label=IntentLabel.ATTACK,
                attack_suppressed=False,
                calibrated_probability=0.82,
            ),
            payload_type=PayloadType.INTENT,
            unit="label",
            provenance=Provenance.DECLARED,
            processing_stage=ProcessingStage.CLASSIFIED,
            producer="test",
            producer_version="0",
            parent_signal_ids=(),
            observed_at_s=100.0,
            produced_at_s=100.1,
            compute_latency_ms=2.0,
            valid_from_s=100.0,
            valid_until_s=110.0,
        )
        restored = KairosSignal.from_dict(sig.to_dict())
        assert isinstance(restored.payload, IntentPayload)
        assert restored.payload.label == IntentLabel.ATTACK
        assert math.isclose(restored.payload.calibrated_probability, 0.82)

    def test_plan_signal_round_trip(self):
        sig = _plan_signal(steps=3, step_interval_s=5.0)
        restored = KairosSignal.from_dict(sig.to_dict())
        assert isinstance(restored.payload, PlanPayload)
        assert restored.payload.steps == 3
        assert restored.payload.step_interval_s == 5.0
        assert restored.payload.targets_w == (200.0, 200.0, 200.0)
        assert restored.payload.observe_only is True

    def test_parent_ids_preserved(self):
        p1, p2 = _sid(), _sid()
        sig = _power_signal(parents=(p1, p2))
        restored = KairosSignal.from_dict(sig.to_dict())
        assert set(restored.parent_signal_ids) == {p1, p2}

    def test_incompatible_schema_version_raises(self):
        sig = _power_signal()
        d = sig.to_dict()
        d["schema_version"] = "99.0"
        with pytest.raises(ValueError, match="schema_version"):
            KairosSignal.from_dict(d)
