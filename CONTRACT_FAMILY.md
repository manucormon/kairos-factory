# CONTRACT_FAMILY.md — Invariants for every Kairos brother

Every brother in this family must satisfy these constraints before being
called verified. These are not recommendations — they are gates.

---

## 0. Automation bias evaluation before building a predictive brother (Guardrail 1)

Any brother that predicts human behavior must evaluate whether its output
improves or worsens human judgment under time pressure before being used
in any non-experimental context. "The human decides in the end" does not
neutralize the risk: time pressure increases over-reliance on automation,
not reduces it.

Required evidence before a predictive brother is considered production-ready:
- A comparison of human decisions with and without the brother's label
- Evaluated under realistic time pressure, not in a reflective lab setting
- Result documented in the brother's NOTES.md

**PROCESS DEVIATION — intent-factory (Brother 02):**
Guardrail 1 existed in FAMILY.md (August 8, 2026) before intent-factory
code was written (August 9, 2026). The evaluation was not performed before
building. This is recorded honestly as a deviation, not corrected retroactively.

Current status of intent-factory:
- `CONSTRUCT_VALIDITY: NOT_EVALUATED`
- Permitted use: experimental / observe-only
- Blocked use: any deployment where intent labels could influence time-critical decisions
- Unblocks when: human-judgment comparison study is completed and documented

## 1. Confidence vocabulary (Guardrail 3)

Every brother declares its own confidence vocabulary before writing code.
No brother mixes labeled and unlabeled values.

| Brother | Vocabulary | Status |
|---|---|---|
| perception-factory | MEASURED / TRACKED / PREDICTED | ✅ declared + tested |
| intent-factory | OBSERVED / CLASSIFIED / PROJECTED | ✅ declared + tested |
| planning-factory | OBSERVED / PLANNED | ✅ declared + tested |
| sensory-architecture-factory | REAL / PROXY / DECLARED | ✅ declared + tested |

Vocabulary must appear in the brother's own CONTRACT.md before any code is written.

## 2. Latency exposed as a first-class variable (Guardrail 8)

Every brother must expose how long its outputs take to compute AND how far
ahead its predictions cover (if applicable).

- A prediction that arrives after the event it was meant to inform is a ghost.
- The `sensory_architecture_factory` (Govern) is the arbiter of human-facing
  output. When a brother's output latency exceeds the event horizon, Govern
  must know to ignore it and fall back to Touch/reflex.
- Required exposure: a documented `latency` field or section in CONTRACT.md
  with measured values, not estimates.

## 3. Verified finding before "done" (Guardrail 2)

Every brother must produce at least one verified finding — a result measured
against real or synthetic ground truth, with a test that confirms it.

- Anomalous results (suspiciously good or bad) are reviewed before reporting.
- The first measured result is a hypothesis; the verified finding is what
  survives scrutiny.
- The finding must be documented in NOTES.md and locked by a test.

## 4. No full autonomy without human approval (Guardrail 4)

No brother makes irreversible decisions without a human in the loop.

- Perceive/Predict: output is observation/estimate only, never action
- Plan: output is suggestions/path-spaces, never commands
- Govern: output is channel arbitration — the human still decides what to do
  with the information that reaches them
- Any brother with a self-revision mechanism requires human approval before
  applying changes to live systems

## 5. CONTRACT.md present and gated (not aspirational)

A capability declared in CONTRACT.md must be implemented and tested.
Declaring `HAS_BOUNCE_DETECTION = True` without a test for it is a lie.
The scaffolder generates placeholders; the contract converts them to facts.

## 6. Real third-party names are a conscious decision (Guardrail 5)

Using a real organization, person, or dataset name in any brother requires
an explicit decision each time — not a default. When in doubt, use a
generic descriptor and note the specific entity in NOTES.md (internal only).

## 7. Scope discipline (Guardrail 7)

A brother does not grow because it can. Every capability addition is reviewed
before acceptance. The question is always: does the brother need this, or is
it being added because the previous brother had it?

---

## Checklist before a brother is verified

- [ ] Confidence vocabulary declared in CONTRACT.md
- [ ] Latency documented with measured values
- [ ] At least one verified finding with a passing test
- [ ] NOTES.md matches registry status (no stale "scaffolded" language)
- [ ] All CONTRACT.md capability flags implemented and tested
- [ ] No unverified specific percentages or citations in prose files
- [ ] Human approval required for any autonomous changes
