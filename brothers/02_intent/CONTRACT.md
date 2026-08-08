# CONTRACT.md — intent_factory (scaffold)

**Status:** identified, not built

## What this brother answers

> "Given another agent making a decision — what is it likely to do?"

This is NOT the same problem as perception-factory (Predict-physics).
A tennis ball obeys gravity; a rival driver obeys their own judgment.
The core cannot be a Kalman filter — it must model behavioral patterns
with a fundamentally different type of uncertainty (irreducible, game-theoretic).

## Boundary with planning-factory (brother 03)

- intent-factory observes an EXTERNAL agent and estimates its behavior
- planning-factory optimizes a path for OUR agent given a known environment
- These are separate problems with separate math — do not merge them

## Capability declarations (to be filled before any code is written)

| Capability | Value | Evidence |
|---|---|---|
| DATA_LABEL_VOCABULARY | TBD | declare before writing code |
| HAS_UNCERTAINTY_ESTIMATE | TBD | |
| LATENCY_MS | TBD | measure before claiming |

## Automation bias warning (Guardrail 1)

Before building this brother, test whether the tool improves or degrades human
judgment under time pressure. "The human decides in the end" does not neutralize
automation bias — research shows time pressure worsens over-reliance on
automated suggestions, not reduces it.

This check must happen BEFORE writing the first line of code, not after.

## Open design questions (resolve before CONTRACT.md is finalized)

1. What is the model core? (Bayesian behavior classification? LSTM? Rule-based FSM?)
2. What training data exists? What label vocabulary does it require?
3. How does the output integrate with sensory-architecture-factory?
   Specifically: what is the latency budget, and what happens when it's exceeded?
