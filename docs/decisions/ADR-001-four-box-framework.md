# ADR-001 — Validity and provisional limits of the four-box framework

**Date:** 2026-08-09
**Status:** Provisionally accepted with documented constraints

---

## Decision

The Kairos family organizes its brothers around a single temporal axis:
Perceive (present) → Predict-physics (near future, known dynamics) →
Predict-intent / Plan (near future, open choices) → Govern (present, human-facing).

This four-box framework is accepted as a provisional organizing taxonomy for
the family. It is not yet claimed as an empirically validated general framework.

---

## Rationale

The axis provides a working reason for why the current capabilities are kept
separate. Each box answers a different operational question, which helps prevent
scope overlap and gives new capabilities an explicit placement test.

The taxonomy is illustrated by individual instances in tennis-ball tracking,
cycling, and utility dispatch. Those examples exercise different subsets of the
family; they do not constitute three independent end-to-end validations. Cycling
is currently the only cross-brother orchestration example.

---

## Known limits and open questions

**Box 02 (Predict-intent) is misnamed.**
The cycling instance classifies *present effort state* (ATTACK/MAINTAIN/RECOVER
from current power, gradient, fatigue) — it does not predict *future intent*.
True temporal intent prediction would require labeled ground truth of what the
cyclist intended to do, which does not exist in public datasets.

The box is better described as "Classify present state from observable signals."
The temporal claim in the name is aspirational, not implemented. This weakens
the temporal coherence of the axis.

Accepted constraint: Box 02 is re-framed as "Classify" for the cycling instance.
The temporal framing may become valid for instances where labeled intent data
exists (e.g., team tactics with GPS + communication logs).

**Box 01 (Perceive + Predict-physics) conflates two things.**
The current brother handles both present perception (where is the ball now?)
and short-horizon physics prediction (where will it be?). These could be
separate boxes. They are combined because no instance currently needs them
separated. If a domain needs pure perception without physics prediction, or
physics prediction at much longer horizons, this should be revisited.

**Not every transition is executed by the orchestrator.**
The cycling pipeline calls the checked-out IntentClassifier and PacingPlanner
and wraps their outputs in KairosSignal. Perception is deliberately absent
because the available tracker is not physically compatible with power data.
The domain governance layer supplies `active_channels`; Kairos performs the
temporal and compatible-channel admission step. A second end-to-end domain is
still needed before claiming the taxonomy generalizes.

---

## Alternatives considered

**Three boxes (Perceive / Plan / Govern):** Would collapse Predict-intent into
Perceive or Plan. Rejected because "classify intent from signals" is a distinct
operation from "track physical position" and from "generate target sequence."

**Five boxes (add a Learn box):** An adaptive calibration layer that updates
thresholds from outcomes. Not built because no instance currently produces
labeled outcomes to learn from. Open for future consideration.

---

## Review trigger

Revisit this ADR if:
- A new brother doesn't fit cleanly into any existing box
- Box 02 is used in a context where labeled intent data exists
- A second domain exercises the same boundaries end to end
