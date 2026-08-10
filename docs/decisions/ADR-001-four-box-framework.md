# ADR-001 — Validity and provisional limits of the four-box framework

**Date:** 2026-08-09
**Status:** Accepted with documented constraints

---

## Decision

The Kairos family organizes its brothers around a single temporal axis:
Perceive (present) → Predict-physics (near future, known dynamics) →
Predict-intent / Plan (near future, open choices) → Govern (present, human-facing).

This four-box framework is accepted as the organizing structure for the family.

---

## Rationale

The axis provides a principled reason for why four brothers exist and not three
or five. Each box answers a different question about time, which prevents scope
overlap and makes it clear where a new capability belongs.

The framework was validated against three instances (tennis ball, cycling, energy
utility dispatch) where the separation held without forcing.

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

**Transition between boxes is not formalized.**
The family contract says brothers communicate via KairosSignal. In practice,
the cycling pipeline in kairos-factory reimplements brothers' logic rather
than calling them. This is a known divergence tracked in
`pipelines/cycling.py` (inline comment) and is a priority fix before any
production use.

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
- The pipeline integration (brothers calling each other) is fully implemented
