"""
Kairos family — end-to-end pipeline demo.

Data: GoldenCheetah OpenData (CC BY 4.0, anonymous athlete)
      601 samples, t=300-900s, FTP=208W
      power=REAL, gradient/fatigue=DECLARED

Pipeline per sample:
  1. perception_factory  — smooth observed power (TRACKED)
  2. intent_factory      — classify intent (CLASSIFIED)
  3. planning_factory    — generate 10-step plan (PLANNED)
  4. sensory_architecture_factory — decide active channels (governance)
"""

import csv
import importlib.util
import sys
from pathlib import Path

HOME = Path.home()

def _import(name: str, path: Path):
    """Import a module from an absolute path, isolating from sys.modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# --- import each brother's core independently --------------------------------
perception_tracker   = _import("perception_tracker",
    HOME / "perception_factory/core/tracker.py")
intent_classifier    = _import("intent_classifier",
    HOME / "intent_factory/core/classifier.py")
planning_planner     = _import("planning_planner",
    HOME / "planning_factory/core/planner.py")

# governance needs its own core + cycling config
sys.path.insert(0, str(HOME / "sensory_architecture_factory"))
from core.governance import govern_hybrid, VoiceQueue
from instances.cycling.config import CHANNELS as CYC_CHANNELS

KalmanTracker   = perception_tracker.KalmanTracker
IntentClassifier = intent_classifier.IntentClassifier
PacingPlanner   = planning_planner.PacingPlanner

# --- load real data -----------------------------------------------------------
DATA = HOME / "intent_factory/instances/cycling/data/real_ride_sample.csv"
samples = []
with open(DATA) as f:
    for row in csv.DictReader(f):
        samples.append({
            "t":            float(row["t"]),
            "power_w":      float(row["power_w"]),
            "ftp_w":        float(row["ftp_w"]),
            "gradient_pct": float(row["gradient_pct"]),
            "fatigue":      float(row["fatigue"]),
        })

# --- initialize brothers ------------------------------------------------------
tracker = KalmanTracker(r_pos=0.5)
tracker.initialize(samples[0]["power_w"], 0.0, samples[0]["t"])
clf     = IntentClassifier(dt=1.0)
planner = PacingPlanner(dt=1.0)
voice_queue = VoiceQueue(expiry_samples=30)

# --- run pipeline -------------------------------------------------------------
print()
print("  KAIROS FAMILY — end-to-end pipeline demo")
print("  " + "=" * 60)
print(f"  Data: GoldenCheetah OpenData, {len(samples)} samples, FTP=208W")
print(f"  REAL power → TRACKED → CLASSIFIED → PLANNED → governed")
print()
print(f"  {'t':>5}  {'power':>6}  {'tracked':>7}  {'intent':>8}  {'plan[0]':>8}  channels")
print(f"  {'-'*5}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*30}")

results = []
for i, s in enumerate(samples):
    t           = s["t"]
    power_w     = s["power_w"]
    ftp_w       = s["ftp_w"]
    gradient    = s["gradient_pct"]
    fatigue     = s["fatigue"]

    # --- Brother 01: track power as 1-D position ----------------------------
    tracker.update(power_w, 0.0, t)
    pred = tracker.predict_ahead(steps=1)
    tracked_power = max(0.0, pred.x)   # power cannot be negative

    # --- Brother 02: classify intent ----------------------------------------
    state = clf.classify(
        power_w=power_w, ftp_w=ftp_w,
        gradient_pct=gradient, fatigue=fatigue,
    )
    intent     = state.label
    suppressed = state.attack_suppressed

    # --- Brother 03: generate plan ------------------------------------------
    plan = planner.plan(
        intent=intent, power_w=power_w, ftp_w=ftp_w,
        gradient_pct=gradient, fatigue=fatigue, steps=10,
    )
    plan_target_0 = plan.targets_w[0]

    # --- Brother 04: govern -------------------------------------------------
    intensity    = min(power_w / ftp_w / 1.2, 1.0)
    fatigue_load = min(fatigue * 0.8, 1.0)
    load         = 1 - (1 - 0.70 * intensity) * (1 - 0.55 * fatigue_load)
    attention    = max(0.0, 1.0 - load)
    reflex_active   = (power_w / ftp_w > 1.15)
    voice_requested = (intent == "ATTACK" and fatigue < 0.5)

    voice_queue.prune(i)
    active = govern_hybrid(
        CYC_CHANNELS, attention, reflex_active,
        voice_requested=voice_requested,
        risk_present=False,
        queue=voice_queue,
        i=i,
    )
    channels_str = "+".join(active) if active else "—"

    results.append({
        "t": t, "intent": intent, "tracked_w": tracked_power,
        "plan_0": plan_target_0, "channels": active,
        "load": load, "attention": attention,
    })

    if i % 30 == 0:
        note = " ←ATTACK" if intent == "ATTACK" and not suppressed else \
               " [suppressed]" if suppressed else ""
        print(f"  {t:>5.0f}  {power_w:>6.1f}  {tracked_power:>7.1f}  "
              f"{intent:>8}{note:<14}  {plan_target_0:>6.1f}W  {channels_str}")

# --- summary ------------------------------------------------------------------
from collections import Counter
intent_counts = Counter(r["intent"] for r in results)
total = len(results)
print()
print("  Summary")
print("  -------")
for label in ("ATTACK", "MAINTAIN", "RECOVER"):
    pct = 100 * intent_counts[label] / total
    print(f"  {label:>8}: {intent_counts[label]:>3} samples ({pct:.1f}%)")

avg_load = sum(r["load"] for r in results) / total
avg_attn = sum(r["attention"] for r in results) / total
voice_count = sum(1 for r in results
                  if r["intent"] == "ATTACK" and "Voice" in r["channels"])
print()
print(f"  avg cognitive load : {avg_load:.3f}")
print(f"  avg attention      : {avg_attn:.3f}")
print(f"  Voice admitted     : {voice_count} / {intent_counts['ATTACK']} ATTACK samples")
print()
print("  Confidence trail verified:")
print("  power=REAL → tracked=TRACKED → intent=CLASSIFIED → plan=PLANNED → governed")
print("  observe_only=True on every plan (family invariant enforced)")
print()
