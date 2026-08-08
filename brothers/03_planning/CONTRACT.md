# CONTRACT.md — planning_factory (scaffold)

**Status:** identified, not built

## What this brother answers

> "Given a known environment (terrain, obstacles, constraints) — what path do we suggest?"

This is NOT the same problem as intent-factory (Predict-intent).
Intent-factory observes an external agent moving through the world.
Planning-factory optimizes a route through a static or slowly-changing environment.
The math is search/optimization, not behavioral classification.

## Hard constraint (from CONTRACT_FAMILY.md §4 and council review)

Output must be framed as **suggestions or path-spaces**, never commands.
If planning-factory outputs commands, it conflicts with sensory-architecture-factory
(the Govern brother), which is the sole arbiter of what reaches the human.
This constraint must appear in the brother's own CONTRACT.md before any code is written.

## Boundary with intent-factory (brother 02)

- planning-factory optimizes for OUR agent given a known, mostly-static environment
- intent-factory predicts what ANOTHER agent will do in a dynamic situation
- A scenario with both (rival driver + route planning) requires both brothers independently

## Capability declarations (to be filled before any code is written)

| Capability | Value | Evidence |
|---|---|---|
| DATA_LABEL_VOCABULARY | TBD | declare before writing code |
| OUTPUT_TYPE | suggestions / path-spaces (never commands) | |
| LATENCY_MS | TBD | measure before claiming |

## Open design questions (resolve before CONTRACT.md is finalized)

1. What search/optimization algorithm? (A*, RRT, gradient descent, other?)
2. How is the environment represented? (grid, graph, continuous space?)
3. How does this brother feed suggestions to sensory-architecture-factory
   without bypassing its arbitration?
