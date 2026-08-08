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

| # | Brother | Repo | Status |
|---|---|---|---|
| 01 | Perceive + Predict-physics | [perception-factory](https://github.com/manucormon/perception-factory) | ✅ verified |
| 02 | Predict-intent | `brothers/02_intent/` | 🔲 identified, not built |
| 03 | Plan | `brothers/03_planning/` | 🔲 identified, not built |
| 04 | Govern | [sensory-architecture-factory](https://github.com/manucormon/sensory-architecture-factory) | ✅ verified |

## Getting started

```bash
git clone --recurse-submodules https://github.com/manucormon/kairos-factory.git
cd kairos-factory

# Run tests for each built brother
pytest brothers/01_perception/instances/tennis_ball/tests/ -v
pytest brothers/04_govern/ -v
```

## Family rules

Before building a new brother, one question: **which box does it fall into?**

- Falls cleanly into an existing box → new *instance* of that brother, not a new brother
- Doesn't fall cleanly into any → pause and design the new core before writing code

See [FAMILY.md](FAMILY.md) for the full framework and eight inherited guardrails.
See [CONTRACT_FAMILY.md](CONTRACT_FAMILY.md) for the technical invariants every brother must satisfy.
