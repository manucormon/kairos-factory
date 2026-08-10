# kairos-factory

**A family of four attention-governance harnesses**, organized around a single axis: time.

> *Kairos* (Greek) — the opportune moment, distinct from Chronos (sequential time).
> The name describes what the family does: not measure time, but find the right moment
> within it.

## The four brothers

```
PAST/PRESENT ──────► FUTURE (physics) ──────► FUTURE (decision) ──────► PRESENT
  Perceive              Predict-physics          Plan                    Govern
"where is it,         "where will it be,       "what path to take,     "what reaches
 right now?"           given known physics?"    given open choices?"    the human, now?"

 World-facing          World-facing             World-facing            Human-facing
```

| # | Brother | Repo | Status | Tests | Data |
|---|---|---|---|---|---|
| 01 | Perceive + Predict-physics | [perception-factory](https://github.com/manucormon/perception-factory) | ✅ verified | 9/9 | MEASURED (real iPhone video) |
| 02 | Classify effort state | [intent-factory](https://github.com/manucormon/intent-factory) | ⚠ implementation verified; construct not evaluated | 10/10 | REAL power + DECLARED gradient/fatigue |
| 03 | Plan | [planning-factory](https://github.com/manucormon/planning-factory) | ✅ verified | 11/11 | REAL input → PLANNED output |
| 04 | Govern | [sensory-architecture-factory](https://github.com/manucormon/sensory-architecture-factory) | ✅ verified | 164/164 | REAL/PROXY/DECLARED per instance |

**All four implementations are built as of August 2026.** Brother 02 remains
experimental/observe-only until its human construct-validity and automation-bias
gate is evaluated. Data: GoldenCheetah OpenData (CC BY 4.0) for brothers 02 and 03.

## Getting started

```bash
git clone --recurse-submodules https://github.com/manucormon/kairos-factory.git
cd kairos-factory

# Run tests for each brother
pytest brothers/01_perception/instances/tennis_ball/tests/ -v
pytest brothers/02_intent/intent-factory/instances/cycling/tests/ -v
pytest brothers/03_planning/planning-factory/instances/cycling/tests/ -v
pytest brothers/04_govern/ -v

# Kairos-level contract and pipeline tests
pytest tests/ -v

# Run the family contract check and all five suites in isolated processes
python3 tools/verify_all.py
```

`pipelines/cycling.py` loads the checked-out IntentClassifier and PacingPlanner
directly from their submodules. It deliberately omits Perception because the
available 2D ball tracker is not physically compatible with power data.

Current package verification: 66 Kairos tests plus 9 Perception, 10 Intent,
11 Planning, and 164 Sensory tests — 260 total.

## Honest limits

**Brother 02 — intent_factory:** `project_ahead(samples, steps)` classifies
a caller-supplied hypothetical sequence — it does NOT forecast from current
state. True temporal intent prediction requires labeled intent data that
does not exist in public cycling datasets. This limit is documented in
[intent-factory CONTRACT.md](brothers/02_intent/intent-factory/instances/cycling/CONTRACT.md).

## Family rules

Before building a new brother, one question: **which box does it fall into?**

- Falls cleanly into an existing box → new *instance* of that brother, not a new brother
- Doesn't fall cleanly into any → pause and design the new core before writing code

See [FAMILY.md](FAMILY.md) for the full framework and eight inherited guardrails.
See [CONTRACT_FAMILY.md](CONTRACT_FAMILY.md) for the technical invariants every brother must satisfy.
