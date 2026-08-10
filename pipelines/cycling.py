"""
pipelines/cycling.py — Cycling-domain orchestration for the Kairos family.

Active path for one cycling moment:
  atomic sensor inputs
      → intent_factory.IntentClassifier
      → planning_factory.PacingPlanner
      → Kairos temporal/channel governance contract

The real brother implementations are loaded from the checked-out submodules;
their classification and planning rules are not copied into this repository.

perception_factory is intentionally omitted: its KalmanTracker models 2D
physical dynamics (position, velocity, gravity, bounce). Watt-level power
tracking is not a compatible physics-tracking problem. ``active_channels`` is
the already-computed output of the domain governance layer; this orchestrator
only admits the generated plan to compatible active channels.

DATA_LABEL: REAL (power_w from GoldenCheetah OpenData, CC BY 4.0);
           PROXY (ftp_w — estimated 95% of best 20-min, ProcessingStage=DERIVED);
           DECLARED (gradient_pct and fatigue — caller-supplied).
"""

from __future__ import annotations

import importlib.util
import math
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, FrozenSet, Optional, Protocol, Tuple

from contracts.kairos_signal import (
    SCHEMA_VERSION,
    FatiguePayload,
    FtpPayload,
    GovernanceDecision,
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
)

INPUT_PRODUCER = "cycling/sensor-input"
INTENT_PRODUCER = "intent-factory/cycling"
PLANNING_PRODUCER = "planning-factory/cycling"
PRODUCER_VERSION = "1.0"
DOMAIN = "cycling"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INTENT_CORE = (
    _REPO_ROOT / "brothers" / "02_intent" / "intent-factory" / "core" / "classifier.py"
)
_PLANNING_CORE = (
    _REPO_ROOT / "brothers" / "03_planning" / "planning-factory" / "core" / "planner.py"
)


def _load_brother_class(module_name: str, path: Path, class_name: str):
    """Load one brother without putting its generic ``core`` package on sys.path."""
    if not path.is_file():
        raise RuntimeError(
            f"Missing Kairos brother at {path}. Clone with --recurse-submodules "
            "or run: git submodule update --init --recursive"
        )
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load module specification for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise RuntimeError(f"{path} does not expose {class_name}") from exc


def _default_intent_classifier():
    classifier_cls = _load_brother_class(
        "_kairos_brother_intent_classifier", _INTENT_CORE, "IntentClassifier"
    )
    return classifier_cls(dt=1.0)


def _default_planner_factory(dt: float):
    planner_cls = _load_brother_class(
        "_kairos_brother_planning_planner", _PLANNING_CORE, "PacingPlanner"
    )
    return planner_cls(dt=dt)


# ---------------------------------------------------------------------------
# Transport protocol — enables MockTransport in tests
# ---------------------------------------------------------------------------

class Transport(Protocol):
    def deliver(self, decision: GovernanceDecision, plan: "KairosSignal[PlanPayload]") -> None:
        ...


class IntentClassifierPort(Protocol):
    def classify(
        self,
        power_w: float,
        ftp_w: float,
        gradient_pct: float = 0.0,
        fatigue: float = 0.0,
    ):
        ...


class PlannerPort(Protocol):
    def plan(
        self,
        intent: str,
        power_w: float,
        ftp_w: float,
        gradient_pct: float = 0.0,
        fatigue: float = 0.0,
        steps: int = 30,
    ):
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

    def __init__(
        self,
        transport: Optional[Transport] = None,
        intent_classifier: Optional[IntentClassifierPort] = None,
        planner_factory: Optional[Callable[[float], PlannerPort]] = None,
    ) -> None:
        self._transport = transport or LoggingTransport()
        self._intent_classifier = intent_classifier or _default_intent_classifier()
        self._planner_factory = planner_factory or _default_planner_factory

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

        if not math.isfinite(plan_horizon_s) or plan_horizon_s <= 0:
            raise ValueError("plan_horizon_s must be positive and finite")
        if not math.isfinite(step_interval_s) or step_interval_s <= 0:
            raise ValueError("step_interval_s must be positive and finite")

        sid = session_id or str(uuid.uuid4())
        steps = max(1, math.ceil(plan_horizon_s / step_interval_s))
        effective_horizon_s = steps * step_interval_s
        input_produced_at_s = time.monotonic()

        # --- Atomic source signals (no incompatible perception model) ---
        power_sig = self._make_signal(
            payload=PowerPayload(power_w=power_w),
            payload_type=PayloadType.POWER,
            unit="W",
            provenance=Provenance.REAL,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=input_produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + effective_horizon_s,
            session_id=sid,
            parents=(),
            producer=INPUT_PRODUCER,
            compute_latency_ms=0.0,
        )
        ftp_sig = self._make_signal(
            payload=FtpPayload(ftp_w=ftp_w),
            payload_type=PayloadType.FTP,
            unit="W",
            provenance=Provenance.PROXY,
            stage=ProcessingStage.DERIVED,
            observed_at_s=observed_at_s,
            produced_at_s=input_produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + effective_horizon_s,
            session_id=sid,
            parents=(),
            producer=INPUT_PRODUCER,
            compute_latency_ms=0.0,
        )
        gradient_sig = self._make_signal(
            payload=GradientPayload(gradient_pct=gradient_pct),
            payload_type=PayloadType.GRADIENT,
            unit="%",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=input_produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + effective_horizon_s,
            session_id=sid,
            parents=(),
            producer=INPUT_PRODUCER,
            compute_latency_ms=0.0,
        )
        fatigue_sig = self._make_signal(
            payload=FatiguePayload(fatigue=fatigue),
            payload_type=PayloadType.FATIGUE,
            unit="",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.MEASURED,
            observed_at_s=observed_at_s,
            produced_at_s=input_produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + effective_horizon_s,
            session_id=sid,
            parents=(),
            producer=INPUT_PRODUCER,
            compute_latency_ms=0.0,
        )

        # --- Brother 02 (intent): classify intent ---
        intent_started_at_s = time.monotonic()
        brother_intent = self._intent_classifier.classify(
            power_w=power_w,
            ftp_w=ftp_w,
            gradient_pct=gradient_pct,
            fatigue=fatigue,
        )
        intent_produced_at_s = time.monotonic()
        intent_label = IntentLabel(brother_intent.label)
        intent_parents = (
            power_sig.signal_id,
            ftp_sig.signal_id,
            gradient_sig.signal_id,
            fatigue_sig.signal_id,
        )
        intent_sig = self._make_signal(
            payload=IntentPayload(
                label=intent_label,
                attack_suppressed=bool(brother_intent.attack_suppressed),
                calibrated_probability=None,
            ),
            payload_type=PayloadType.INTENT,
            unit="label",
            provenance=Provenance.DECLARED,
            stage=ProcessingStage.CLASSIFIED,
            observed_at_s=observed_at_s,
            produced_at_s=intent_produced_at_s,
            valid_from_s=observed_at_s,
            valid_until_s=observed_at_s + effective_horizon_s,
            session_id=sid,
            parents=intent_parents,
            producer=INTENT_PRODUCER,
            compute_latency_ms=(intent_produced_at_s - intent_started_at_s) * 1000.0,
        )

        # --- Brother 03 (planning): build plan ---
        planner = self._planner_factory(step_interval_s)
        plan_started_at_s = time.monotonic()
        brother_plan = planner.plan(
            intent=intent_label.value,
            power_w=power_w,
            ftp_w=ftp_w,
            gradient_pct=gradient_pct,
            fatigue=fatigue,
            steps=steps,
        )
        plan_produced_at_s = time.monotonic()
        if brother_plan.observe_only is not True:
            raise RuntimeError("planning_factory violated observe_only family invariant")
        expected_horizon_s = effective_horizon_s
        if not math.isclose(
            brother_plan.dt_ahead, expected_horizon_s, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise RuntimeError(
                "planning_factory dt_ahead does not match steps * step_interval_s"
            )
        targets = tuple(brother_plan.targets_w)
        if len(targets) != steps:
            raise RuntimeError("planning_factory returned the wrong number of targets")
        plan_parents = (
            power_sig.signal_id,
            ftp_sig.signal_id,
            gradient_sig.signal_id,
            fatigue_sig.signal_id,
            intent_sig.signal_id,
        )
        plan_valid_from = observed_at_s
        plan_valid_until = observed_at_s + brother_plan.dt_ahead

        plan_sig: KairosSignal[PlanPayload] = KairosSignal(
            schema_version=SCHEMA_VERSION,
            signal_id=str(uuid.uuid4()),
            domain=DOMAIN,
            session_id=sid,
            payload=PlanPayload(
                targets_w=targets,
                steps=steps,
                step_interval_s=step_interval_s,
                observe_only=True,
            ),
            payload_type=PayloadType.PLAN,
            unit="W",
            provenance=Provenance.DECLARED,
            processing_stage=ProcessingStage.PLANNED,
            producer=PLANNING_PRODUCER,
            producer_version=PRODUCER_VERSION,
            parent_signal_ids=plan_parents,
            observed_at_s=observed_at_s,
            produced_at_s=plan_produced_at_s,
            compute_latency_ms=(plan_produced_at_s - plan_started_at_s) * 1000.0,
            valid_from_s=plan_valid_from,
            valid_until_s=plan_valid_until,
        )

        # --- Brother 04 (sensory governance): evaluate and deliver ---
        decision = build_governance_decision(
            signal=plan_sig,
            now_s=time.monotonic(),
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
        producer: str,
        compute_latency_ms: float,
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
            producer=producer,
            producer_version=PRODUCER_VERSION,
            parent_signal_ids=parents,
            observed_at_s=observed_at_s,
            produced_at_s=produced_at_s,
            compute_latency_ms=compute_latency_ms,
            valid_from_s=valid_from_s,
            valid_until_s=valid_until_s,
        )
