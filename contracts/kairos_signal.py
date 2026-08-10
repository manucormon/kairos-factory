"""
contracts/kairos_signal.py — Shared inter-brother contract for the Kairos family.

KairosSignal[T] is the typed envelope every brother uses to pass data to the next.
Provenance and processing_stage travel with every value; lineage is preserved via
parent_signal_ids. GovernanceDecision separates temporal eligibility, admission, and
channel arbitration so that a stale plan never silences a domain reflex.

Schema version: 1.0
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Generic, List, Optional, Tuple, Type, TypeVar

T = TypeVar("T")

SCHEMA_VERSION = "1.0"
COMPATIBLE_VERSIONS: FrozenSet[str] = frozenset({"1.0"})


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Provenance(str, Enum):
    REAL     = "REAL"       # direct sensor reading
    PROXY    = "PROXY"      # stand-in value — may or may not be calibrated
    DECLARED = "DECLARED"   # design parameter, threshold, or assumed estimate


class ProcessingStage(str, Enum):
    MEASURED   = "MEASURED"    # direct sensor read, no transformation
    DERIVED    = "DERIVED"     # computed from one or more measured values (GPS gradient, FTP estimate)
    TRACKED    = "TRACKED"     # state-filter estimate (Kalman, etc.)
    PREDICTED  = "PREDICTED"   # physics-based forward projection
    CLASSIFIED = "CLASSIFIED"  # label inferred from observed state
    PLANNED    = "PLANNED"     # target sequence from a planner


class IntentLabel(str, Enum):
    ATTACK   = "ATTACK"
    MAINTAIN = "MAINTAIN"
    RECOVER  = "RECOVER"


class PayloadType(str, Enum):
    POWER    = "PowerPayload"
    FTP      = "FtpPayload"
    GRADIENT = "GradientPayload"
    FATIGUE  = "FatiguePayload"
    INTENT   = "IntentPayload"
    PLAN     = "PlanPayload"


class GovernanceReason(str, Enum):
    VALID                 = "VALID"
    NOT_YET_VALID         = "NOT_YET_VALID"          # now < valid_from_s
    STALE                 = "STALE"                  # now >= valid_until_s
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"  # valid_until_s < event_at_s
    EVENT_PASSED          = "EVENT_PASSED"            # event_at_s < now
    FUTURE_TIMESTAMP      = "FUTURE_TIMESTAMP"        # observed_at or produced_at > now


class DeliveryReason(str, Enum):
    DELIVERED             = "DELIVERED"
    BUDGET_BLOCKED        = "BUDGET_BLOCKED"
    NO_COMPATIBLE_CHANNEL = "NO_COMPATIBLE_CHANNEL"
    TEMPORALLY_INELIGIBLE = "TEMPORALLY_INELIGIBLE"  # signal not VALID


# ---------------------------------------------------------------------------
# Payloads — one field, one provenance
# ---------------------------------------------------------------------------

def _check_finite(*values: float, context: str) -> None:
    for v in values:
        if not math.isfinite(v):
            raise ValueError(f"{context}: all float fields must be finite, got {v}")


@dataclass(frozen=True)
class PowerPayload:
    power_w: float  # >= 0

    def __post_init__(self) -> None:
        _check_finite(self.power_w, context="PowerPayload")
        if self.power_w < 0:
            raise ValueError(f"PowerPayload.power_w must be >= 0, got {self.power_w}")


@dataclass(frozen=True)
class FtpPayload:
    ftp_w: float  # > 0; callers must validate provenance = PROXY

    def __post_init__(self) -> None:
        _check_finite(self.ftp_w, context="FtpPayload")
        if self.ftp_w <= 0:
            raise ValueError(f"FtpPayload.ftp_w must be > 0, got {self.ftp_w}")


@dataclass(frozen=True)
class GradientPayload:
    # Range [-20, 20] matching existing intent/planning/sensory contracts.
    # Clipping to a narrower range is the pipeline's responsibility.
    gradient_pct: float

    def __post_init__(self) -> None:
        _check_finite(self.gradient_pct, context="GradientPayload")
        if not -20.0 <= self.gradient_pct <= 20.0:
            raise ValueError(
                f"GradientPayload.gradient_pct must be in [-20, 20], got {self.gradient_pct}"
            )


@dataclass(frozen=True)
class FatiguePayload:
    fatigue: float  # [0.0, 1.0]; callers must validate provenance = DECLARED

    def __post_init__(self) -> None:
        _check_finite(self.fatigue, context="FatiguePayload")
        if not 0.0 <= self.fatigue <= 1.0:
            raise ValueError(
                f"FatiguePayload.fatigue must be in [0, 1], got {self.fatigue}"
            )


@dataclass(frozen=True)
class IntentPayload:
    label:                  IntentLabel
    attack_suppressed:      bool
    calibrated_probability: Optional[float]  # [0, 1] if calibrated; None if not

    def __post_init__(self) -> None:
        if self.calibrated_probability is not None:
            _check_finite(self.calibrated_probability, context="IntentPayload")
            if not 0.0 <= self.calibrated_probability <= 1.0:
                raise ValueError(
                    "IntentPayload.calibrated_probability must be in [0, 1], "
                    f"got {self.calibrated_probability}"
                )


@dataclass(frozen=True)
class PlanPayload:
    targets_w:       Tuple[float, ...]   # len == steps; each >= 0 and finite
    steps:           int                  # > 0
    step_interval_s: float               # > 0; horizon = steps * step_interval_s
    observe_only:    bool                # always True — family invariant

    def __post_init__(self) -> None:
        if self.steps <= 0:
            raise ValueError(f"PlanPayload.steps must be > 0, got {self.steps}")
        _check_finite(self.step_interval_s, context="PlanPayload.step_interval_s")
        if self.step_interval_s <= 0:
            raise ValueError(
                f"PlanPayload.step_interval_s must be > 0, got {self.step_interval_s}"
            )
        if len(self.targets_w) != self.steps:
            raise ValueError(
                f"PlanPayload.targets_w length ({len(self.targets_w)}) "
                f"must equal steps ({self.steps})"
            )
        for i, t in enumerate(self.targets_w):
            if not math.isfinite(t) or t < 0:
                raise ValueError(
                    f"PlanPayload.targets_w[{i}] must be finite and >= 0, got {t}"
                )
        if not self.observe_only:
            raise ValueError("PlanPayload.observe_only must always be True (family invariant)")


# Maps PayloadType to its class — used for from_dict() and cross-validation
PAYLOAD_CLASSES: Dict[PayloadType, Type] = {
    PayloadType.POWER:    PowerPayload,
    PayloadType.FTP:      FtpPayload,
    PayloadType.GRADIENT: GradientPayload,
    PayloadType.FATIGUE:  FatiguePayload,
    PayloadType.INTENT:   IntentPayload,
    PayloadType.PLAN:     PlanPayload,
}


# ---------------------------------------------------------------------------
# KairosSignal[T]
# ---------------------------------------------------------------------------

def _is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(s, version=4)
        return True
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class KairosSignal(Generic[T]):
    # identity
    schema_version:    str
    signal_id:         str
    domain:            str
    session_id:        str

    # content — name is derived from payload_type; no separate name field
    payload:           T
    payload_type:      PayloadType
    unit:              str            # "W", "label", "%", ""

    # provenance — one label per atomic signal
    provenance:        Provenance
    processing_stage:  ProcessingStage
    producer:          str
    producer_version:  str
    parent_signal_ids: Tuple[str, ...]   # UUIDs; no self-ref; no duplicates

    # time — four separate instants; compute_latency uses monotonic clock
    observed_at_s:      float
    produced_at_s:      float
    compute_latency_ms: float
    valid_from_s:       float
    valid_until_s:      float

    def __post_init__(self) -> None:
        # schema version
        if self.schema_version not in COMPATIBLE_VERSIONS:
            raise ValueError(
                f"schema_version '{self.schema_version}' not in {COMPATIBLE_VERSIONS}"
            )
        # UUIDs
        if not _is_valid_uuid(self.signal_id):
            raise ValueError(f"signal_id is not a valid UUID v4: {self.signal_id!r}")
        if not _is_valid_uuid(self.session_id):
            raise ValueError(f"session_id is not a valid UUID v4: {self.session_id!r}")
        for pid in self.parent_signal_ids:
            if not _is_valid_uuid(pid):
                raise ValueError(f"parent_signal_id is not a valid UUID v4: {pid!r}")
        # no self-reference
        if self.signal_id in self.parent_signal_ids:
            raise ValueError("signal_id must not appear in parent_signal_ids")
        # no duplicate parents
        if len(self.parent_signal_ids) != len(set(self.parent_signal_ids)):
            raise ValueError("parent_signal_ids must not contain duplicates")
        # payload type matches payload class
        expected_cls = PAYLOAD_CLASSES[self.payload_type]
        if not isinstance(self.payload, expected_cls):
            raise ValueError(
                f"payload_type={self.payload_type.value} but payload is "
                f"{type(self.payload).__name__}"
            )
        # time invariants
        for name, val in [
            ("observed_at_s", self.observed_at_s),
            ("produced_at_s", self.produced_at_s),
            ("compute_latency_ms", self.compute_latency_ms),
            ("valid_from_s", self.valid_from_s),
            ("valid_until_s", self.valid_until_s),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")
        if self.observed_at_s > self.produced_at_s:
            raise ValueError(
                f"observed_at_s ({self.observed_at_s}) must be <= "
                f"produced_at_s ({self.produced_at_s})"
            )
        if self.valid_from_s < self.observed_at_s:
            raise ValueError(
                f"valid_from_s ({self.valid_from_s}) must be >= "
                f"observed_at_s ({self.observed_at_s})"
            )
        if self.valid_until_s <= self.valid_from_s:
            raise ValueError(
                f"valid_until_s ({self.valid_until_s}) must be > "
                f"valid_from_s ({self.valid_from_s})"
            )
        if self.compute_latency_ms < 0:
            raise ValueError(
                f"compute_latency_ms must be >= 0, got {self.compute_latency_ms}"
            )
        # for PlanPayload: horizon must match steps * step_interval_s
        if isinstance(self.payload, PlanPayload):
            expected_horizon = self.payload.steps * self.payload.step_interval_s
            actual_horizon = self.valid_until_s - self.valid_from_s
            if not math.isclose(actual_horizon, expected_horizon, rel_tol=1e-6):
                raise ValueError(
                    f"PlanPayload horizon mismatch: "
                    f"valid_until_s - valid_from_s = {actual_horizon:.6f}s "
                    f"but steps × step_interval_s = {expected_horizon:.6f}s"
                )

    # --- serialization ---

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        # convert enums to their string values
        d["provenance"]       = self.provenance.value
        d["processing_stage"] = self.processing_stage.value
        d["payload_type"]     = self.payload_type.value
        # IntentLabel inside IntentPayload
        if self.payload_type == PayloadType.INTENT:
            d["payload"]["label"] = self.payload.label.value
        # tuples become lists in asdict; mark them for from_dict
        d["parent_signal_ids"] = list(self.parent_signal_ids)
        if self.payload_type == PayloadType.PLAN:
            d["payload"]["targets_w"] = list(self.payload.targets_w)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "KairosSignal":
        if data.get("schema_version") not in COMPATIBLE_VERSIONS:
            raise ValueError(
                f"schema_version '{data.get('schema_version')}' not compatible"
            )
        payload_type = PayloadType(data["payload_type"])
        raw = dict(data["payload"])
        if payload_type == PayloadType.INTENT:
            raw["label"] = IntentLabel(raw["label"])
        if payload_type == PayloadType.PLAN:
            raw["targets_w"] = tuple(raw["targets_w"])
        payload = PAYLOAD_CLASSES[payload_type](**raw)
        return cls(
            schema_version=data["schema_version"],
            signal_id=data["signal_id"],
            domain=data["domain"],
            session_id=data["session_id"],
            payload=payload,
            payload_type=payload_type,
            unit=data["unit"],
            provenance=Provenance(data["provenance"]),
            processing_stage=ProcessingStage(data["processing_stage"]),
            producer=data["producer"],
            producer_version=data["producer_version"],
            parent_signal_ids=tuple(data["parent_signal_ids"]),
            observed_at_s=data["observed_at_s"],
            produced_at_s=data["produced_at_s"],
            compute_latency_ms=data["compute_latency_ms"],
            valid_from_s=data["valid_from_s"],
            valid_until_s=data["valid_until_s"],
        )


# ---------------------------------------------------------------------------
# Temporal validation
# ---------------------------------------------------------------------------

def check_temporality(
    signal: KairosSignal,
    now_s: float,
    event_at_s: float,
) -> GovernanceReason:
    """
    Evaluate temporal eligibility of a signal. Order matters:
    1. FUTURE_TIMESTAMP — clocks are inconsistent
    2. EVENT_PASSED     — the event already happened; signal is irrelevant
    3. NOT_YET_VALID    — signal exists but hasn't activated yet
    4. STALE            — signal has expired
    5. INSUFFICIENT_COVERAGE — signal won't cover until the event
    6. VALID
    """
    if signal.observed_at_s > now_s or signal.produced_at_s > now_s:
        return GovernanceReason.FUTURE_TIMESTAMP
    if event_at_s < now_s:
        return GovernanceReason.EVENT_PASSED
    if now_s < signal.valid_from_s:
        return GovernanceReason.NOT_YET_VALID
    if now_s >= signal.valid_until_s:
        return GovernanceReason.STALE
    if signal.valid_until_s < event_at_s:
        return GovernanceReason.INSUFFICIENT_COVERAGE
    return GovernanceReason.VALID


# ---------------------------------------------------------------------------
# GovernanceDecision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceDecision:
    # temporal eligibility: True only when validity_reason == VALID
    temporally_eligible: bool
    validity_reason:     GovernanceReason

    # plan admission: True only when delivery_reason == DELIVERED
    signal_admitted:     bool
    delivery_reason:     DeliveryReason

    # channels — active is system-wide (may include Touch from domain reflex);
    # delivery carries THIS plan; delivery ⊆ active
    active_channels:   Tuple[str, ...]
    delivery_channels: Tuple[str, ...]

    # traceability
    evaluated_signal_id: str
    evaluated_at_s:      float
    event_at_s:          float

    def __post_init__(self) -> None:
        # derived invariants
        if self.temporally_eligible != (self.validity_reason == GovernanceReason.VALID):
            raise ValueError(
                "temporally_eligible must equal (validity_reason == VALID)"
            )
        if self.signal_admitted != (self.delivery_reason == DeliveryReason.DELIVERED):
            raise ValueError(
                "signal_admitted must equal (delivery_reason == DELIVERED)"
            )
        if not self.signal_admitted and self.delivery_channels:
            raise ValueError(
                "delivery_channels must be empty when signal_admitted=False"
            )
        # delivery ⊆ active
        active_set   = set(self.active_channels)
        delivery_set = set(self.delivery_channels)
        if not delivery_set.issubset(active_set):
            raise ValueError(
                f"delivery_channels {delivery_set} must be a subset of "
                f"active_channels {active_set}"
            )
        # no duplicates
        if len(self.active_channels) != len(active_set):
            raise ValueError("active_channels must not contain duplicates")
        if len(self.delivery_channels) != len(delivery_set):
            raise ValueError("delivery_channels must not contain duplicates")
        # time fields finite
        for name, val in [("evaluated_at_s", self.evaluated_at_s),
                          ("event_at_s", self.event_at_s)]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")


def build_governance_decision(
    signal: "KairosSignal",
    now_s: float,
    event_at_s: float,
    active_channels: Tuple[str, ...],
    compatible_delivery_channels: FrozenSet[str],
) -> GovernanceDecision:
    """
    Build a GovernanceDecision for a plan signal.

    active_channels:              computed by govern_hybrid (system-wide; includes Touch if reflex)
    compatible_delivery_channels: channels capable of carrying THIS payload type

    A plan is delivered only when:
      - temporally_eligible (validity_reason == VALID)
      - at least one compatible channel is in active_channels (budget permits)

    A stale/insufficient plan never silences Touch or any other domain reflex —
    active_channels reflects the domain state regardless of plan validity.
    """
    reason = check_temporality(signal, now_s, event_at_s)
    temporally_eligible = (reason == GovernanceReason.VALID)

    if not temporally_eligible:
        return GovernanceDecision(
            temporally_eligible=False,
            validity_reason=reason,
            signal_admitted=False,
            delivery_reason=DeliveryReason.TEMPORALLY_INELIGIBLE,
            active_channels=active_channels,        # domain reflex preserved
            delivery_channels=(),
            evaluated_signal_id=signal.signal_id,
            evaluated_at_s=now_s,
            event_at_s=event_at_s,
        )

    # eligible — arbitrate delivery channels
    active_set = set(active_channels)
    deliverable = tuple(sorted(
        ch for ch in compatible_delivery_channels if ch in active_set
    ))

    if deliverable:
        return GovernanceDecision(
            temporally_eligible=True,
            validity_reason=GovernanceReason.VALID,
            signal_admitted=True,
            delivery_reason=DeliveryReason.DELIVERED,
            active_channels=active_channels,
            delivery_channels=deliverable,
            evaluated_signal_id=signal.signal_id,
            evaluated_at_s=now_s,
            event_at_s=event_at_s,
        )

    # eligible but no compatible channel open
    budget_open = bool(active_set - {"Touch"})  # non-reflex channels exist
    delivery_reason = (
        DeliveryReason.BUDGET_BLOCKED if budget_open
        else DeliveryReason.NO_COMPATIBLE_CHANNEL
    )
    return GovernanceDecision(
        temporally_eligible=True,
        validity_reason=GovernanceReason.VALID,
        signal_admitted=False,
        delivery_reason=delivery_reason,
        active_channels=active_channels,
        delivery_channels=(),
        evaluated_signal_id=signal.signal_id,
        evaluated_at_s=now_s,
        event_at_s=event_at_s,
    )
